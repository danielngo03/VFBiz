import { describe, expect, it } from "vitest";
import {
  hasExactOrigin,
  hasValidCsrfToken,
} from "../src/http/request-security";

describe("request security", () => {
  it("requires an exact, non-empty origin", () => {
    expect(hasExactOrigin(new Request("https://portal.example.test"))).toBe(false);
    expect(
      hasExactOrigin(
        new Request("https://portal.example.test", {
          headers: { origin: "https://portal.example.test" },
        }),
      ),
    ).toBe(true);
    expect(
      hasExactOrigin(
        new Request("https://portal.example.test", {
          headers: { origin: "https://evil.example.test" },
        }),
      ),
    ).toBe(false);
  });

  it("compares the CSRF token without accepting length mismatches", () => {
    const valid = new Request("https://portal.example.test", {
      headers: { "x-csrf-token": "expected" },
    });
    const invalid = new Request("https://portal.example.test", {
      headers: { "x-csrf-token": "expected-extra" },
    });
    expect(hasValidCsrfToken(valid, "expected")).toBe(true);
    expect(hasValidCsrfToken(invalid, "expected")).toBe(false);
  });
});
