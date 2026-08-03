import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("public shell has a meaningful accessible entry point", async ({
  page,
}) => {
  const cspViolations: string[] = [];
  page.on("console", (message) => {
    if (/content security policy|refused to/iu.test(message.text())) {
      cspViolations.push(message.text());
    }
  });

  const response = await page.goto("/");
  expect(response?.ok()).toBe(true);
  await expect(
    page.getByRole("heading", {
      name: "Quản lý trải nghiệm sở hữu xe tại một nơi",
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Đăng nhập" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Tạo tài khoản" })).toBeVisible();
  await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");

  await page.keyboard.press("Tab");
  const skipLink = page.getByRole("link", {
    name: "Bỏ qua tới nội dung chính",
  });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(
    accessibility.violations.filter((violation) =>
      ["critical", "serious"].includes(violation.impact ?? ""),
    ),
  ).toEqual([]);

  await page.setViewportSize({ height: 800, width: 320 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(cspViolations).toEqual([]);
});

test("foundation responses include defensive browser headers", async ({
  request,
}) => {
  const response = await request.get("/");
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
  expect(response.headers()["x-frame-options"]).toBe("DENY");
  expect(
    response.headers()["content-security-policy"] ??
      response.headers()["content-security-policy-report-only"],
  ).toContain("frame-ancestors 'none'");
});

test("anonymous visitors cannot open the authenticated Chat page", async ({
  request,
}) => {
  const response = await request.get("/chat", { maxRedirects: 0 });
  expect(response.status()).toBe(307);
  const location = response.headers().location;
  expect(location).toBeTruthy();
  expect(new URL(location!, "http://localhost:3001").searchParams.get("returnTo")).toBe(
    "/chat",
  );
});
