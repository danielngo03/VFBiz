import { expect, test } from "@playwright/test";

const challenge = "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD";

function authorizationUrl(realm, client, callback) {
  const query = new URLSearchParams({
    client_id: client,
    redirect_uri: callback,
    response_type: "code",
    scope: "openid",
    code_challenge: challenge,
    code_challenge_method: "S256",
    state: `identity-theme-${realm}`,
    nonce: `identity-theme-${realm}`,
  });
  return `/realms/${realm}/protocol/openid-connect/auth?${query}`;
}

test("customer renders the localized theme and registration", async ({
  page,
}) => {
  const remoteRequests = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) {
      remoteRequests.push(request.url());
    }
  });

  await page.goto(
    authorizationUrl(
      "vfbiz-customer",
      "vfbiz-customer-bff",
      "http://localhost:3001/api/auth/callback",
    ),
  );

  await expect(
    page.getByRole("heading", { name: "Đăng nhập tài khoản khách hàng" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Đăng ký" })).toBeVisible();
  await expect(page.locator('link[href*="vfbiz-customer.css"]')).toHaveCount(1);
  expect(remoteRequests).toEqual([]);

  await page.getByRole("link", { name: "Quên mật khẩu?" }).click();
  await expect(
    page.getByRole("heading", { name: "Khôi phục mật khẩu" }),
  ).toBeVisible();

  await page.goBack();
  await page.getByRole("link", { name: "Đăng ký" }).click();
  await expect(
    page.getByRole("heading", { name: "Tạo tài khoản khách hàng" }),
  ).toBeVisible();
});

test("workforce renders its theme without self-registration", async ({
  page,
}) => {
  await page.goto(
    authorizationUrl(
      "vfbiz-workforce",
      "vfbiz-workforce-bff",
      "http://localhost:3002/api/auth/callback",
    ),
  );

  await expect(
    page.getByRole("heading", { name: "Đăng nhập Workforce" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Đăng ký" })).toHaveCount(0);
  await expect(page.locator('link[href*="vfbiz-workforce.css"]')).toHaveCount(
    1,
  );
});

test("customer English locale is available", async ({ page }) => {
  const url = authorizationUrl(
    "vfbiz-customer",
    "vfbiz-customer-bff",
    "http://localhost:3001/api/auth/callback",
  );
  await page.goto(`${url}&ui_locales=en`);
  await expect(
    page.getByRole("heading", { name: "Customer sign in" }),
  ).toBeVisible();
});
