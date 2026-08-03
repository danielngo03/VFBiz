import { freshnessDescriptors } from "../../src/domain/freshness/freshness";

test("every freshness state has a non-color label", () => {
  expect(Object.values(freshnessDescriptors).every(({ label }) => label.length > 0)).toBe(true);
});
