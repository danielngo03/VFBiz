import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const required = process.env.CUSTOMER_E2E_REQUIRED === "true";
const enabled = required || process.env.CUSTOMER_E2E_ENABLED === "true";
const email = process.env.CUSTOMER_E2E_EMAIL;
const password = process.env.CUSTOMER_E2E_PASSWORD;

if (required && (email === undefined || password === undefined)) {
  throw new Error(
    "Required Garage E2E needs CUSTOMER_E2E_EMAIL and CUSTOMER_E2E_PASSWORD.",
  );
}

test.skip(
  !enabled || email === undefined || password === undefined,
  "Requires Portal, Keycloak, Redis, PostgreSQL, API and an approved catalog.",
);

async function login(page: Page): Promise<void> {
  await page.goto("/api/auth/login?returnTo=/account/garage");
  await page.locator("#username").fill(email!);
  await page.locator("#password").fill(password!);
  await page.locator("#kc-login").click();
  await page.waitForURL(/\/account\/garage(?:\?|$)/u);
}

test("customer completes the Garage lifecycle without entering VIN", async ({
  page,
}) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Xe của bạn" })).toBeVisible();
  expect(await page.locator('[name*="vin" i]').count()).toBe(0);

  const addButton = page.getByRole("button", { name: "Thêm vào Garage" });
  test.skip(
    !(await addButton.isVisible()),
    "The approved catalog has no fresh active model/variant.",
  );

  const nickname = `Garage E2E ${Date.now()}`;
  await page.getByLabel("Tên gợi nhớ (không bắt buộc)").fill(nickname);
  await addButton.click();
  await expect(page.getByText(nickname, { exact: true })).toBeVisible();
  await expect(page.getByText("Chưa xác minh").last()).toBeVisible();

  const card = page
    .getByRole("article")
    .filter({ has: page.getByText(nickname, { exact: true }) });
  const renamed = `${nickname} đã đổi`;
  await card.getByLabel("Tên gợi nhớ").fill(renamed);
  await card.getByRole("button", { name: "Đổi tên" }).click();
  await expect(page.getByText(renamed, { exact: true })).toBeVisible();

  const renamedCard = page
    .getByRole("article")
    .filter({ has: page.getByText(renamed, { exact: true }) });
  const primary = renamedCard.getByRole("button", {
    name: "Đặt làm xe chính",
  });
  if (await primary.isVisible()) {
    await primary.click();
    await expect(renamedCard.getByText("Xe chính")).toBeVisible();
  }

  await renamedCard.getByRole("button", { name: "Xóa xe" }).click();
  await page.getByRole("button", { name: "Xóa khỏi Garage" }).click();
  await expect(page.getByText(renamed, { exact: true })).toHaveCount(0);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(
    accessibility.violations.filter((violation) =>
      ["critical", "serious"].includes(violation.impact ?? ""),
    ),
  ).toEqual([]);
});
