import { resourceFreshness } from "../../src/platform/network/connectivity";

test.each([
  [{ connectivity: "offline", hasData: true, stale: false, error: false }, "offline"],
  [{ connectivity: "unknown", hasData: false, stale: false, error: false }, "unknown"],
  [{ connectivity: "online", hasData: false, stale: false, error: true }, "restricted"],
  [{ connectivity: "online", hasData: true, stale: false, error: true }, "stale"],
  [{ connectivity: "online", hasData: true, stale: false, error: false }, "fresh"],
] as const)("maps resource state to explicit freshness", (input, expected) => {
  expect(resourceFreshness(input)).toBe(expected);
});
