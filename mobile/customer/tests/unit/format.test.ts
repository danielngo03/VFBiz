import { formatCustomerDateTime } from "../../src/platform/i18n/format";

test("formats API timestamps and fails safely for invalid values", () => {
  expect(formatCustomerDateTime("invalid")).toBe("Chưa xác định");
  expect(formatCustomerDateTime("2026-07-30T10:00:00.000Z", "en-US")).toContain("2026");
});
