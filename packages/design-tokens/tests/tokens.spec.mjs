import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");

test("generated CSS is self-contained and contains no remote resource", async () => {
  for (const file of ["base.css", "customer.css", "workforce.css"]) {
    const css = await readFile(resolve(root, "generated", file), "utf8");
    assert.match(css, /--vfbiz-/u);
    assert.doesNotMatch(css, /url\s*\(|@import|https?:/iu);
  }
});

test("semantic variants expose the same required accent contract", async () => {
  for (const file of ["customer.css", "workforce.css"]) {
    const css = await readFile(resolve(root, "generated", file), "utf8");
    assert.match(css, /--vfbiz-accent:/u);
    assert.match(css, /--vfbiz-accent-strong:/u);
    assert.match(css, /--vfbiz-on-accent:/u);
    assert.match(css, /--vfbiz-canvas:/u);
    assert.match(css, /prefers-color-scheme: dark/u);
  }
});
