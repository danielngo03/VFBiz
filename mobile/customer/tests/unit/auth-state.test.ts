import { authReducer, initialAuthState } from "../../src/domain/session/session";

const credential = {
  accessToken: "synthetic-access-token",
  tokenType: "Bearer",
  expiresAt: 1_900_000_000_000,
  subject: "subject-test-001",
  issuer: "https://identity.example.test/realms/customer",
  clientId: "customer-mobile",
  environment: "development",
  market: "VN",
};

test("auth state restores and signs out without retaining credential", () => {
  const restored = authReducer(initialAuthState, { type: "RESTORED", credential });
  expect(restored.status).toBe("authenticated");
  expect(authReducer(restored, { type: "SIGNED_OUT" })).toEqual({
    status: "anonymous",
    credential: null,
    error: null,
  });
});
