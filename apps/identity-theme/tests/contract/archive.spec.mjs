import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import test from "node:test";

const workspace = resolve(import.meta.dirname, "../..");

test("customer and workforce themes inherit the shared foundation", async () => {
  for (const theme of ["vfbiz-customer", "vfbiz-workforce"]) {
    const properties = await readFile(
      join(
        workspace,
        "src/main/resources/theme",
        theme,
        "login/theme.properties",
      ),
      "utf8",
    );
    assert.match(properties, /^parent=vfbiz-foundation$/m);
    assert.match(properties, /^locales=vi,en$/m);
  }
});

test("foundation inherits Keycloak and remains abstract", async () => {
  const properties = await readFile(
    join(
      workspace,
      "src/main/resources/theme/vfbiz-foundation/login/theme.properties",
    ),
    "utf8",
  );
  assert.match(properties, /^parent=keycloak$/m);
  assert.match(properties, /^abstract=true$/m);
});

test("workforce messages do not advertise self-registration", async () => {
  for (const locale of ["vi", "en"]) {
    const messages = await readFile(
      join(
        workspace,
        `src/main/resources/theme/vfbiz-workforce/login/messages/messages_${locale}.properties`,
      ),
      "utf8",
    );
    assert.doesNotMatch(messages, /Create account|Tạo tài khoản/i);
  }
});

test("the only FreeMarker override is the shared email shell", async () => {
  const template = await readFile(
    join(
      workspace,
      "src/main/resources/theme/vfbiz-foundation/email/html/template.ftl",
    ),
    "utf8",
  );
  assert.match(template, /<#macro emailLayout>/);
  assert.match(template, /<#nested>/);
  assert.match(template, /msg\("emailFooter"\)/);
});
