import assert from "node:assert/strict";
import test from "node:test";
import { parseServerActionAllowedOrigins } from "../../next.config";

test("Server Action origin allowlist accepts exact hosts only", () => {
  assert.deepEqual(
    parseServerActionAllowedOrigins("portal.example.com, localhost:3001"),
    ["portal.example.com", "localhost:3001"],
  );

  for (const value of [
    "*",
    "*.example.com",
    "https://portal.example.com",
    "portal.example.com/path",
    "user@portal.example.com",
    "portal..example.com",
  ]) {
    assert.throws(
      () => parseServerActionAllowedOrigins(value),
      /Invalid CUSTOMER_SERVER_ACTION_ALLOWED_ORIGINS entry/u,
    );
  }
});
