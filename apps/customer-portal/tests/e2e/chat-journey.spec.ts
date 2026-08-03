import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const required = process.env.CUSTOMER_CHAT_E2E_REQUIRED === "true";
const enabled = required || process.env.CUSTOMER_CHAT_E2E_ENABLED === "true";
const email = process.env.CUSTOMER_E2E_EMAIL;
const password = process.env.CUSTOMER_E2E_PASSWORD;
const question =
  process.env.CUSTOMER_CHAT_E2E_QUESTION ??
  "Nếu chưa có nguồn đã duyệt, hãy từ chối trả lời thông tin bảo hành.";

if (required && (email === undefined || password === undefined)) {
  throw new Error(
    "Required Chat E2E needs CUSTOMER_E2E_EMAIL and CUSTOMER_E2E_PASSWORD.",
  );
}

test.skip(
  !enabled || email === undefined || password === undefined,
  "Requires the authenticated staging Portal, API, private AI service and test credentials.",
);

async function login(page: Page): Promise<void> {
  await page.goto("/api/auth/login?returnTo=/chat");
  await page.locator("#username").fill(email!);
  await page.locator("#password").fill(password!);
  await page.locator("#kc-login").click();
  await page.waitForURL(/\/chat(?:\?|$)/u);
}

test("authenticated Chat preserves citations or refusal and revokes the browser session", async ({
  page,
}) => {
  await login(page);
  await expect(
    page.getByRole("heading", { name: "Trợ lý khách hàng" }),
  ).toBeVisible();
  await expect(page.getByText("Authenticated staging")).toBeVisible();

  const before = await page.evaluate(() => ({
    local: Object.keys(localStorage),
    session: Object.keys(sessionStorage),
  }));
  expect(JSON.stringify(before)).not.toMatch(/access[_-]?token|refresh[_-]?token/iu);

  await page.getByRole("button", { name: "Bắt đầu phiên kiểm thử" }).click();
  await expect(page.getByText("Sẵn sàng", { exact: true })).toBeVisible();
  await page.getByLabel("Nội dung tin nhắn").fill(question);
  await page.getByRole("button", { name: "Gửi", exact: true }).click();

  const assistant = page.locator(".chat-message-assistant").last();
  await expect(assistant).toBeVisible({ timeout: 30_000 });
  const hasCitation = await assistant.getByText(/Nguồn tham chiếu/iu).isVisible();
  const hasRefusal = await assistant.getByText(/từ chối an toàn/iu).isVisible();
  expect(hasCitation || hasRefusal).toBe(true);

  const violations = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(
    violations.violations.filter((item) =>
      ["critical", "serious"].includes(item.impact ?? ""),
    ),
  ).toEqual([]);

  await page.getByRole("button", { name: "Đóng phiên" }).click();
  await page.getByRole("button", { name: "Xác nhận đóng phiên" }).click();
  await expect(page.getByText(/Phiên đã đóng/iu)).toBeVisible();

  const security = await page.evaluate(async () => {
    const response = await fetch("/api/auth/security", { cache: "no-store" });
    return (await response.json()) as { csrfToken: string };
  });
  const logoutStatus = await page.evaluate(async (csrfToken) => {
    const response = await fetch("/api/auth/logout", {
      headers: { "x-csrf-token": csrfToken },
      method: "POST",
    });
    return response.status;
  }, security.csrfToken);
  expect(logoutStatus).toBe(200);
  await page.goto("/chat");
  await page.waitForURL(/\/api\/auth\/login/iu);
});
