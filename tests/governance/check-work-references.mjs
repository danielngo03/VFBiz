#!/usr/bin/env node
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { findMissingWorkReferences } from "../../tools/check-work-references.mjs";

const temporary = await mkdtemp(path.join(os.tmpdir(), "vfbiz-work-refs-"));
const workRoot = path.join(temporary, "work");
const itemRoot = path.join(workRoot, "items");
let failures = 0;

function assert(condition, message) {
  if (!condition) {
    failures += 1;
    process.stderr.write(`- ${message}\n`);
  }
}

try {
  await mkdir(path.join(workRoot, "plans"), { recursive: true });
  await mkdir(path.join(workRoot, "archive"), { recursive: true });
  await mkdir(itemRoot, { recursive: true });
  await writeFile(path.join(itemRoot, "VFBIZ-0001.md"), "# VFBIZ-0001\n");
  await writeFile(
    path.join(workRoot, "plans", "active.md"),
    "Depends on VFBIZ-0001 and VFBIZ-9999.\n",
  );
  await writeFile(
    path.join(workRoot, "archive", "history.md"),
    "Historical VFBIZ-8888 is intentionally outside the active registry.\n",
  );

  const broken = await findMissingWorkReferences({ workRoot, itemRoot });
  assert(
    broken.missing.length === 1 &&
      broken.missing[0].includes("VFBIZ-9999"),
    "active plans must report a dangling work-item reference",
  );
  assert(
    !broken.missing.some((entry) => entry.includes("VFBIZ-8888")),
    "archive history must remain outside the active reference gate",
  );

  await writeFile(path.join(itemRoot, "VFBIZ-9999.md"), "# VFBIZ-9999\n");
  const repaired = await findMissingWorkReferences({ workRoot, itemRoot });
  assert(
    repaired.missing.length === 0,
    "adding the canonical item must close the active reference",
  );
} finally {
  await rm(temporary, { recursive: true, force: true });
}

if (failures > 0) process.exit(1);
process.stdout.write(
  "Work-reference tests passed: active plans fail closed and archive history remains isolated.\n",
);
