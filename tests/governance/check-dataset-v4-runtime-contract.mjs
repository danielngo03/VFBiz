#!/usr/bin/env node

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const output = execFileSync(
  process.execPath,
  ["tools/check-runtime-contracts.mjs", "--self-test"],
  {
    cwd: root,
    encoding: "utf8",
  },
);

assert.match(
  output,
  /Dataset v4 authority self-test passed/,
  "runtime contract self-test must exercise v4 semantic authority",
);
assert.match(
  output,
  /dataset-release-manifest\/v4/,
  "runtime contract gate must identify v4 as the active dataset manifest",
);

console.log("Dataset v4 runtime contract authority verified.");
