import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const challenge = "EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE";

test("customer login has no serious accessibility violation", async ({
  page,
}) => {
  const query = new URLSearchParams({
    client_id: "vfbiz-customer-bff",
    redirect_uri: "http://localhost:3001/api/auth/callback",
    response_type: "code",
    scope: "openid",
    code_challenge: challenge,
    code_challenge_method: "S256",
    state: "identity-a11y",
    nonce: "identity-a11y",
  });
  await page.goto(
    `/realms/vfbiz-customer/protocol/openid-connect/auth?${query}`,
  );

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(({ impact }) =>
    ["serious", "critical"].includes(impact ?? ""),
  );

  expect(serious).toEqual([]);
});

test("workforce dark mobile login remains accessible and does not overflow", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await page.setViewportSize({ width: 390, height: 844 });
  const query = new URLSearchParams({
    client_id: "vfbiz-workforce-bff",
    redirect_uri: "http://localhost:3002/api/auth/callback",
    response_type: "code",
    scope: "openid",
    code_challenge: challenge,
    code_challenge_method: "S256",
    state: "identity-a11y-workforce",
    nonce: "identity-a11y-workforce",
  });
  await page.goto(
    `/realms/vfbiz-workforce/protocol/openid-connect/auth?${query}`,
  );

  const sizes = await page.locator("html").evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(sizes.scrollWidth).toBeLessThanOrEqual(sizes.clientWidth);

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  const serious = results.violations.filter(({ impact }) =>
    ["serious", "critical"].includes(impact ?? ""),
  );
  expect(serious).toEqual([]);
});
