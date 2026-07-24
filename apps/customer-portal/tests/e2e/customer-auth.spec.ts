import { expect, test, type Page } from "@playwright/test";

const required = process.env.CUSTOMER_E2E_REQUIRED === "true";
const enabled = required || process.env.CUSTOMER_E2E_ENABLED === "true";
const email = process.env.CUSTOMER_E2E_EMAIL;
const password = process.env.CUSTOMER_E2E_PASSWORD;

if (required && (email === undefined || password === undefined)) {
  throw new Error(
    "Required Customer Portal E2E needs CUSTOMER_E2E_EMAIL and CUSTOMER_E2E_PASSWORD.",
  );
}

test.skip(
  !enabled || email === undefined || password === undefined,
  "Requires a running local Portal, Keycloak, Redis and API with dedicated E2E credentials.",
);

async function login(page: Page): Promise<void> {
  await page.goto("/api/auth/login?returnTo=/account");
  await page.locator("#username").fill(email!);
  await page.locator("#password").fill(password!);
  await page.locator("#kc-login").click();
  await page.waitForURL(/\/account(?:\?|$)/u);
  await expect(
    page.getByRole("heading", { name: "Tổng quan tài khoản" }),
  ).toBeVisible();
}

async function securityState(page: Page) {
  return page.evaluate(async () => {
    const response = await fetch("/api/auth/security", {
      cache: "no-store",
      credentials: "include",
    });
    return {
      body: (await response.json()) as {
        csrfToken?: string;
        emailVerified?: boolean;
      },
      status: response.status,
    };
  });
}

async function authenticatedMutation(
  page: Page,
  path: string,
  method: "DELETE" | "POST",
  csrfToken?: string,
) {
  return page.evaluate(
    async ({ csrfToken: token, method: requestMethod, path: requestPath }) => {
      const response = await fetch(requestPath, {
        cache: "no-store",
        credentials: "include",
        headers: token === undefined ? {} : { "x-csrf-token": token },
        method: requestMethod,
      });
      return {
        body:
          response.status === 204
            ? null
            : ((await response.json()) as Record<string, unknown>),
        status: response.status,
      };
    },
    { csrfToken, method, path },
  );
}

test("login, CSRF, refresh and logout use only the opaque BFF session", async ({
  page,
}) => {
  await login(page);
  const storage = await page.evaluate(() => ({
    cookie: document.cookie,
    local: Object.keys(localStorage),
    session: Object.keys(sessionStorage),
  }));
  expect(JSON.stringify(storage)).not.toMatch(
    /access[_-]?token|refresh[_-]?token/iu,
  );

  const security = await securityState(page);
  expect(security.status).toBe(200);
  expect(security.body.emailVerified).toBe(true);
  expect(security.body.csrfToken).toBeTruthy();

  expect(
    (await authenticatedMutation(page, "/api/auth/refresh", "POST")).status,
  ).toBe(403);
  expect(
    (
      await authenticatedMutation(
        page,
        "/api/auth/refresh",
        "POST",
        security.body.csrfToken,
      )
    ).status,
  ).toBe(204);

  const logout = await authenticatedMutation(
    page,
    "/api/auth/logout",
    "POST",
    security.body.csrfToken,
  );
  expect(logout.status).toBe(200);
  expect(["confirmed", "pending", "retry_required"]).toContain(
    logout.body?.providerReconciliation,
  );
  expect((await securityState(page)).status).toBe(401);
});

test("logout-all revokes every local portal session before returning", async ({
  page,
}) => {
  await login(page);
  const security = await securityState(page);
  const result = await authenticatedMutation(
    page,
    "/api/auth/sessions",
    "DELETE",
    security.body.csrfToken,
  );
  expect(result.status).toBe(200);
  expect(Number(result.body?.revokedCount)).toBeGreaterThanOrEqual(1);
  expect((await securityState(page)).status).toBe(401);
});

test("Keycloak subject logout reaches the back-channel endpoint", async ({
  page,
  request,
}) => {
  const keycloakUrl = process.env.CUSTOMER_E2E_KEYCLOAK_ADMIN_URL;
  const adminUser = process.env.CUSTOMER_E2E_KEYCLOAK_ADMIN_USER;
  const adminPassword = process.env.CUSTOMER_E2E_KEYCLOAK_ADMIN_PASSWORD;
  const realm = process.env.CUSTOMER_E2E_KEYCLOAK_REALM ?? "vfbiz-customer";
  test.skip(
    !keycloakUrl || !adminUser || !adminPassword,
    "Back-channel acceptance requires dedicated Keycloak admin E2E credentials.",
  );

  await login(page);
  const tokenResponse = await request.post(
    `${keycloakUrl}/realms/master/protocol/openid-connect/token`,
    {
      form: {
        client_id: "admin-cli",
        grant_type: "password",
        password: adminPassword!,
        username: adminUser!,
      },
    },
  );
  expect(tokenResponse.ok()).toBe(true);
  const { access_token: adminToken } = (await tokenResponse.json()) as {
    access_token: string;
  };
  const usersResponse = await request.get(
    `${keycloakUrl}/admin/realms/${realm}/users`,
    {
      headers: { authorization: `Bearer ${adminToken}` },
      params: { exact: "true", username: email! },
    },
  );
  expect(usersResponse.ok()).toBe(true);
  const users = (await usersResponse.json()) as Array<{ id: string }>;
  expect(users).toHaveLength(1);
  const logoutResponse = await request.post(
    `${keycloakUrl}/admin/realms/${realm}/users/${users[0]!.id}/logout`,
    { headers: { authorization: `Bearer ${adminToken}` } },
  );
  expect(logoutResponse.ok()).toBe(true);
  await expect.poll(async () => (await securityState(page)).status).toBe(401);
});
