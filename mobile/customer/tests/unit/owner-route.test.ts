import { ownerRouteDecision } from "../../src/platform/auth/owner-route";

test("protected owner routes fail closed without an authenticated credential", () => {
  expect(ownerRouteDecision("restoring", false)).toBe("loading");
  expect(ownerRouteDecision("error", true)).toBe("sign-in");
  expect(ownerRouteDecision("anonymous", false)).toBe("sign-in");
  expect(ownerRouteDecision("authenticated", true)).toBe("owner");
});
