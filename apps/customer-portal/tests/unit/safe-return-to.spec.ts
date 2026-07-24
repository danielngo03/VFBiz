import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  customerReturnToOrDefault,
  normalizeCustomerReturnTo,
} from "../../src/platform/auth/safe-return-to";
import { customerAuthHref } from "../../src/platform/auth/bff-client";

describe("customer return URL validation", () => {
  it("keeps a same-origin portal path including query and fragment", () => {
    assert.equal(
      normalizeCustomerReturnTo("/account/garage?tab=primary#vehicle"),
      "/account/garage?tab=primary#vehicle",
    );
  });

  it("rejects external, backslash and encoded redirect variants", () => {
    const unsafe = [
      "https://evil.example/account",
      "//evil.example/account",
      "/\\evil.example/account",
      "/%5cevil.example/account",
      "/%255cevil.example/account",
      "/%2f%2fevil.example/account",
      "/%252f%252fevil.example/account",
      "/account%0d%0aLocation:%20https://evil.example",
    ];
    for (const value of unsafe) {
      assert.equal(normalizeCustomerReturnTo(value), null, value);
      assert.equal(customerReturnToOrDefault(value), "/account", value);
      assert.equal(customerAuthHref("login", value), "/api/auth/login", value);
    }
  });
});
