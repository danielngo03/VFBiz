#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import {
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "../..");
const canonical = JSON.parse(
  await readFile(
    path.join(
      ROOT,
      "docs/architecture/customer-assistant-capability-maturity.json",
    ),
    "utf8",
  ),
);
const temporary = await mkdtemp(path.join(os.tmpdir(), "vfbiz-maturity-"));
const source = path.join(temporary, "maturity.json");
const output = path.join(temporary, "maturity.md");
let failures = 0;

function assert(condition, message) {
  if (!condition) {
    failures += 1;
    process.stderr.write(`- ${message}\n`);
  }
}

function run(write = false) {
  return spawnSync(
    process.execPath,
    [
      path.join(ROOT, "tools/capability-maturity.mjs"),
      ...(write ? ["--write"] : []),
    ],
    {
      cwd: ROOT,
      encoding: "utf8",
      env: {
        ...process.env,
        VFBIZ_MATURITY_SOURCE: source,
        VFBIZ_MATURITY_OUTPUT: output,
      },
    },
  );
}

try {
  await writeFile(source, `${JSON.stringify(canonical, null, 2)}\n`);
  assert(run(true).status === 0, "valid maturity source must render");
  assert(run().status === 0, "fresh maturity output must validate");

  const missingVerification = structuredClone(canonical);
  missingVerification.entries[0].evidence =
    missingVerification.entries[0].evidence.filter(
      ({ kind }) => kind !== "verification-spec",
    );
  await writeFile(
    source,
    `${JSON.stringify(missingVerification, null, 2)}\n`,
  );
  const missing = run(true);
  assert(
    missing.status !== 0 &&
      missing.stderr.includes(
        "Implemented requires verification-spec evidence",
      ),
    "Implemented status must fail without verification-spec evidence",
  );

  const escaping = structuredClone(canonical);
  escaping.entries[0].evidence[0].path = "../outside";
  await writeFile(source, `${JSON.stringify(escaping, null, 2)}\n`);
  assert(
    run(true).status !== 0,
    "maturity evidence path traversal must fail closed",
  );

  await writeFile(source, `${JSON.stringify(canonical, null, 2)}\n`);
  assert(run(true).status === 0, "valid source must render after negative cases");
  await writeFile(output, "stale\n");
  const stale = run();
  assert(
    stale.status !== 0 && stale.stderr.includes("is stale"),
    "stale generated maturity output must fail",
  );
} finally {
  await rm(temporary, { recursive: true, force: true });
}

if (failures > 0) process.exit(1);
process.stdout.write(
  "Capability maturity tests passed: status evidence, path safety and drift fail closed.\n",
);
