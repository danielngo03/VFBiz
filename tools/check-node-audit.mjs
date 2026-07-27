import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";

const policyPath = new URL("../security/node-audit-exceptions.json", import.meta.url);
const policy = JSON.parse(await readFile(policyPath, "utf8"));
const today = new Date().toISOString().slice(0, 10);
const approved = new Map(
  policy.exceptions.map((entry) => [String(entry.advisory), entry]),
);

const audit = spawnSync(
  "npm",
  ["audit", "--omit=dev", "--audit-level=high", "--json"],
  { cwd: process.cwd(), encoding: "utf8", maxBuffer: 20 * 1024 * 1024 },
);

if (!audit.stdout.trim()) {
  process.stderr.write(audit.stderr);
  throw new Error("npm audit did not return a JSON report");
}

const report = JSON.parse(audit.stdout);
const findings = [];
for (const [packageName, vulnerability] of Object.entries(
  report.vulnerabilities ?? {},
)) {
  for (const advisory of vulnerability.via ?? []) {
    if (
      typeof advisory === "object" &&
      ["high", "critical"].includes(advisory.severity)
    ) {
      findings.push({
        advisory: String(advisory.source),
        packageName,
        severity: advisory.severity,
        title: advisory.title,
      });
    }
  }
}

const violations = [];
for (const finding of findings) {
  const exception = approved.get(finding.advisory);
  if (!exception) {
    violations.push(`${finding.severity} ${finding.packageName}: ${finding.title}`);
    continue;
  }
  if (exception.package !== finding.packageName) {
    violations.push(
      `exception ${finding.advisory} is scoped to ${exception.package}, not ${finding.packageName}`,
    );
  }
  if (exception.expiresOn < today) {
    violations.push(
      `exception ${finding.advisory} expired on ${exception.expiresOn}`,
    );
  }
}

for (const exception of policy.exceptions) {
  if (!findings.some((finding) => finding.advisory === String(exception.advisory))) {
    violations.push(
      `stale exception ${exception.advisory}; remove it because the finding is gone`,
    );
  }
}

if (violations.length > 0) {
  process.stderr.write(`${violations.join("\n")}\n`);
  process.exit(1);
}

process.stdout.write(
  `Node audit passed with ${findings.length} reviewed, unexpired exception(s).\n`,
);
