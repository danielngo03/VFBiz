import assert from "node:assert/strict";
import test from "node:test";
import {
  CustomerBffClient,
  MemoryOnlyCsrfToken,
  customerAuthHref,
  vehicleVerificationLabel,
  type JsonFetch,
} from "../../src/index.ts";

test("customer client uses same-origin BFF cookie and never constructs an authorization header", async () => {
  const observed: Array<{ path: string; init: Parameters<JsonFetch>[1] }> = [];
  const fetchImplementation: JsonFetch = async (path, init) => {
    observed.push({ path, init });
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  };
  const csrf = new MemoryOnlyCsrfToken();
  csrf.set("runtime-generated-csrf");
  const client = new CustomerBffClient(fetchImplementation, csrf);
  await client.get("/bff/account/profile");
  await client.mutate("/bff/account/consent", { state: "withdrawn" });
  await client.delete("/bff/account/sessions");
  assert.equal(
    observed.every(({ init }) => init.credentials === "include"),
    true,
  );
  assert.equal(
    observed.some(({ init }) => "authorization" in init.headers),
    false,
  );
  assert.equal(
    observed[1].init.headers["x-csrf-token"],
    "runtime-generated-csrf",
  );
  assert.equal(observed[2].init.method, "DELETE");
  assert.equal(
    observed[2].init.headers["x-csrf-token"],
    "runtime-generated-csrf",
  );
});

test("garage exposes the unverified state explicitly", () => {
  assert.equal(vehicleVerificationLabel("unverified"), "Chưa xác minh");
});

test("customer auth links stay same-origin and never embed external return URLs", () => {
  assert.equal(
    customerAuthHref("login", "/account/garage"),
    "/api/auth/login?returnTo=%2Faccount%2Fgarage",
  );
  assert.equal(customerAuthHref("register"), "/api/auth/register");
  assert.equal(
    customerAuthHref("login", "https://evil.example/steal"),
    "/api/auth/login",
  );
  assert.equal(customerAuthHref("reset-password"), "/api/auth/reset-password");
  assert.equal(
    customerAuthHref("configure-mfa", "/account/security"),
    "/api/auth/configure-mfa?returnTo=%2Faccount%2Fsecurity",
  );
});

test("portal source never names or forwards NestJS legacy token cookies", async () => {
  const { readFile } = await import("node:fs/promises");
  const files = [
    "src/platform/auth/bff-client.ts",
    "src/platform/api/customer-api.ts",
    "src/platform/session/current-session.ts",
  ];
  const source = (
    await Promise.all(files.map((file) => readFile(file, "utf8")))
  ).join("\n");
  assert.doesNotMatch(source, /vfbiz_customer_(access|refresh|csrf)/u);
  assert.doesNotMatch(source, /headers:\s*\{[^}]*cookie/isu);
  assert.match(source, /credentials:\s*"omit"/u);
});
