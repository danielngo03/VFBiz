#!/usr/bin/env node
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const SNAPSHOT = path.resolve(
  process.env.VFBIZ_DEPENDENCY_RISK_SNAPSHOT ??
    path.join(ROOT, "docs/governance/dependency-risk-snapshot.json"),
);
const snapshot = JSON.parse(await readFile(SNAPSHOT, "utf8"));
const lockPath = path.resolve(
  process.env.VFBIZ_DEPENDENCY_LOCKFILE ??
    path.join(ROOT, snapshot.lockfile?.path ?? ""),
);
const errors = [];

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sortedUnique(values) {
  return [...new Set(values)].sort();
}

function advisoryId(item) {
  if (typeof item !== "object" || item === null) return null;
  const match = String(item.url ?? "").match(/GHSA-[a-z0-9-]+/i);
  return match?.[0] ?? `npm-${item.source}`;
}

function collectAdvisories(report, packageName, visited = new Set()) {
  if (visited.has(packageName)) return [];
  visited.add(packageName);
  const item = report.vulnerabilities?.[packageName];
  if (!item) return [];
  return sortedUnique(
    (item.via ?? []).flatMap((via) =>
      typeof via === "string"
        ? collectAdvisories(report, via, visited)
        : [advisoryId(via)].filter(Boolean),
    ),
  );
}

function validateException(exception, index) {
  const prefix = `exceptions[${index}]`;
  if (exception.status !== "approved")
    errors.push(`${prefix}.status must be approved`);
  if (!Array.isArray(exception.packages) || exception.packages.length === 0)
    errors.push(`${prefix}.packages must be non-empty`);
  if (
    !Array.isArray(exception.advisories) ||
    exception.advisories.length === 0
  )
    errors.push(`${prefix}.advisories must be non-empty`);
  if (!exception.owner) errors.push(`${prefix}.owner is required`);
  if (!exception.scope) errors.push(`${prefix}.scope is required`);
  if (!exception.mitigation) errors.push(`${prefix}.mitigation is required`);
  if (!/^VFBIZ-\d{4}$/.test(exception.removalWorkItem ?? ""))
    errors.push(`${prefix}.removalWorkItem must be a Work Item ID`);
  if (!exception.approval?.authority)
    errors.push(`${prefix}.approval.authority is required`);
  if (!/^[a-f0-9]{64}$/.test(exception.approval?.digest ?? ""))
    errors.push(`${prefix}.approval.digest must be SHA-256`);
  if (!Number.isFinite(Date.parse(exception.expiresAt)))
    errors.push(`${prefix}.expiresAt must be a valid timestamp`);
}

if (snapshot.schemaVersion !== 1)
  errors.push("dependency risk snapshot schemaVersion must be 1");
if (snapshot.auditCommand !== "npm audit --omit=dev --json")
  errors.push("dependency risk snapshot must pin the production audit command");

const lockDigest = sha256(await readFile(lockPath));
if (lockDigest !== snapshot.lockfile?.sha256)
  errors.push(
    `dependency risk snapshot lockfile digest is stale: observed ${lockDigest}`,
  );

const expectedPackages = sortedUnique(snapshot.vulnerablePackages ?? []);
if (expectedPackages.length !== (snapshot.vulnerablePackages ?? []).length)
  errors.push("vulnerablePackages must be sorted and unique");
const expectedAdvisories = sortedUnique(snapshot.advisories ?? []);
if (expectedAdvisories.length !== (snapshot.advisories ?? []).length)
  errors.push("advisories must be sorted and unique");
if (!Number.isInteger(snapshot.severityCounts?.high))
  errors.push("severityCounts.high must be an integer");
if (!Number.isInteger(snapshot.severityCounts?.critical))
  errors.push("severityCounts.critical must be an integer");
(snapshot.exceptions ?? []).forEach(validateException);

const live = process.argv.includes("--live");
if (live) {
  const auditFile = process.env.VFBIZ_DEPENDENCY_AUDIT_FILE;
  let auditText;
  if (auditFile) {
    auditText = await readFile(path.resolve(auditFile), "utf8");
  } else {
    const audit = spawnSync("npm", ["audit", "--omit=dev", "--json"], {
      cwd: ROOT,
      encoding: "utf8",
      maxBuffer: 20 * 1024 * 1024,
    });
    auditText = audit.stdout;
    if (!auditText) errors.push("production dependency audit returned no JSON");
  }

  if (auditText) {
    let report;
    try {
      report = JSON.parse(auditText);
    } catch {
      errors.push("production dependency audit output is not valid JSON");
    }
    if (report) {
      const observed = report.metadata?.vulnerabilities ?? {};
      const observedPackages = sortedUnique(
        Object.entries(report.vulnerabilities ?? {})
          .filter(([, item]) => ["high", "critical"].includes(item.severity))
          .map(([name]) => name),
      );
      const observedAdvisories = sortedUnique(
        observedPackages.flatMap((name) => collectAdvisories(report, name)),
      );
      if (
        observed.high !== snapshot.severityCounts.high ||
        observed.critical !== snapshot.severityCounts.critical
      )
        errors.push(
          `live severity counts drifted: high=${observed.high}, critical=${observed.critical}`,
        );
      if (JSON.stringify(observedPackages) !== JSON.stringify(expectedPackages))
        errors.push("live vulnerable package set drifted from the snapshot");
      if (
        JSON.stringify(observedAdvisories) !==
        JSON.stringify(expectedAdvisories)
      )
        errors.push("live advisory identity set drifted from the snapshot");

      const activeExceptions = (snapshot.exceptions ?? []).filter(
        (exception) =>
          exception.status === "approved" &&
          Date.parse(exception.expiresAt) > Date.now(),
      );
      const unexcepted = observedPackages.filter(
        (name) => {
          const required = collectAdvisories(report, name);
          return !activeExceptions.some(
            (exception) =>
              exception.packages.includes(name) &&
              required.every((id) => exception.advisories.includes(id)),
          );
        },
      );
      if (unexcepted.length > 0)
        errors.push(
          `staging blocked by unexcepted high/critical packages: ${unexcepted.join(", ")}`,
        );
    }
  }
}

if (errors.length > 0) {
  errors.forEach((error) => process.stderr.write(`- ${error}\n`));
  process.exit(1);
}

process.stdout.write(
  live
    ? "Live production dependency graph matches the accepted staging policy.\n"
    : "Dependency risk snapshot is bound to the current lockfile.\n",
);
