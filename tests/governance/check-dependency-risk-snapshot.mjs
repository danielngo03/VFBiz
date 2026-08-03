#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "../..");
const temporary = await mkdtemp(path.join(os.tmpdir(), "vfbiz-dependency-risk-"));
const lockfile = path.join(temporary, "package-lock.json");
const snapshotFile = path.join(temporary, "snapshot.json");
const auditFile = path.join(temporary, "audit.json");
let failures = 0;

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function run(live = false) {
  return spawnSync(
    process.execPath,
    [
      path.join(ROOT, "tools/check-dependency-risk-snapshot.mjs"),
      ...(live ? ["--live"] : []),
    ],
    {
      cwd: ROOT,
      encoding: "utf8",
      env: {
        ...process.env,
        VFBIZ_DEPENDENCY_RISK_SNAPSHOT: snapshotFile,
        VFBIZ_DEPENDENCY_LOCKFILE: lockfile,
        VFBIZ_DEPENDENCY_AUDIT_FILE: auditFile,
      },
    },
  );
}

function assert(condition, message) {
  if (!condition) {
    failures += 1;
    process.stderr.write(`- ${message}\n`);
  }
}

try {
  const lock = "{\"lockfileVersion\":3}\n";
  const snapshot = {
    schemaVersion: 1,
    observedAt: "2026-07-29T00:00:00+07:00",
    auditCommand: "npm audit --omit=dev --json",
    lockfile: { path: "package-lock.json", sha256: digest(lock) },
    severityCounts: { high: 1, critical: 0 },
    vulnerablePackages: ["example-package"],
    advisories: ["GHSA-aaaa-bbbb-cccc"],
    exceptions: [],
  };
  const audit = {
    metadata: { vulnerabilities: { high: 1, critical: 0 } },
    vulnerabilities: {
      "example-package": {
        severity: "high",
        via: [
          {
            source: 1234,
            url: "https://github.com/advisories/GHSA-aaaa-bbbb-cccc",
          },
        ],
      },
    },
  };

  await writeFile(lockfile, lock);
  await writeFile(snapshotFile, `${JSON.stringify(snapshot)}\n`);
  await writeFile(auditFile, `${JSON.stringify(audit)}\n`);
  assert(run().status === 0, "current lockfile digest must validate");

  await writeFile(lockfile, `${lock}changed\n`);
  assert(run().status !== 0, "lockfile drift must fail closed");
  await writeFile(lockfile, lock);

  const liveBlocked = run(true);
  assert(
    liveBlocked.status !== 0 &&
      liveBlocked.stderr.includes("staging blocked"),
    "unexcepted high finding must block staging",
  );

  snapshot.exceptions = [
    {
      status: "approved",
      packages: ["example-package"],
      advisories: ["GHSA-aaaa-bbbb-cccc"],
      owner: "security-owner",
      scope: "staging only",
      mitigation: "disable the affected endpoint and monitor rejected traffic",
      removalWorkItem: "VFBIZ-0197",
      expiresAt: "2999-01-01T00:00:00Z",
      approval: {
        authority: "security-owner",
        digest: "a".repeat(64),
      },
    },
  ];
  await writeFile(snapshotFile, `${JSON.stringify(snapshot)}\n`);
  assert(run(true).status === 0, "active scoped exception may satisfy the gate");

  snapshot.exceptions[0].approval.digest = "not-a-digest";
  await writeFile(snapshotFile, `${JSON.stringify(snapshot)}\n`);
  assert(run(true).status !== 0, "incomplete approval evidence must fail closed");
  snapshot.exceptions[0].approval.digest = "a".repeat(64);
  await writeFile(snapshotFile, `${JSON.stringify(snapshot)}\n`);

  audit.vulnerabilities["example-package"].via[0].url =
    "https://github.com/advisories/GHSA-dddd-eeee-ffff";
  await writeFile(auditFile, `${JSON.stringify(audit)}\n`);
  assert(run(true).status !== 0, "advisory identity drift must fail closed");
  audit.vulnerabilities["example-package"].via[0].url =
    "https://github.com/advisories/GHSA-aaaa-bbbb-cccc";

  audit.vulnerabilities["new-package"] = { severity: "high" };
  audit.metadata.vulnerabilities.high = 2;
  await writeFile(auditFile, `${JSON.stringify(audit)}\n`);
  assert(run(true).status !== 0, "live advisory drift must fail closed");
} finally {
  await rm(temporary, { recursive: true, force: true });
}

if (failures > 0) process.exit(1);
process.stdout.write(
  "Dependency risk tests passed: lock drift, live drift and unexcepted findings fail closed.\n",
);
