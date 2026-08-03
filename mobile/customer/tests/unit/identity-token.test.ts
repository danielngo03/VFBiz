import { validateIdentityToken } from "../../src/platform/auth/jwt-subject";

function token(payload: Record<string, unknown>): string {
  const encoded = globalThis.btoa(JSON.stringify(payload)).replace(/=/gu, "").replace(/\+/gu, "-").replace(/\//gu, "_");
  return `synthetic.${encoded}.not-a-production-signature`;
}

const expected = {
  issuer: "https://identity.example.test/realms/customer",
  clientId: "customer-mobile",
  nonce: "nonce-001",
  now: 1_900_000_000_000,
};

test("binds identity claims to issuer, audience, nonce and expiry", () => {
  expect(validateIdentityToken(token({
    sub: "subject-001",
    iss: expected.issuer,
    aud: expected.clientId,
    nonce: expected.nonce,
    exp: 1_900_000_100,
  }), expected)).toBe("subject-001");
});

test.each([
  ["issuer", { iss: "https://attacker.example" }],
  ["audience", { aud: "another-client" }],
  ["nonce", { nonce: "another-nonce" }],
  ["expired", { exp: 1_899_999_999 }],
])("rejects an identity token with invalid %s", (_name, override) => {
  expect(() => validateIdentityToken(token({
    sub: "subject-001",
    iss: expected.issuer,
    aud: expected.clientId,
    nonce: expected.nonce,
    exp: 1_900_000_100,
    ...override,
  }), expected)).toThrow();
});
