#!/usr/bin/env node
import { access, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = path.resolve(
  process.env.VFBIZ_MATURITY_SOURCE ??
    path.join(
      ROOT,
      "docs/architecture/customer-assistant-capability-maturity.json",
    ),
);
const OUTPUT = path.resolve(
  process.env.VFBIZ_MATURITY_OUTPUT ??
    path.join(
      ROOT,
      "docs/architecture/customer-assistant-capability-maturity.md",
    ),
);
const VALID_STATUSES = new Set([
  "Implemented",
  "Candidate",
  "Target-only",
  "Human-blocked",
]);
const REQUIRED_EVIDENCE_KINDS = {
  Implemented: new Set([
    "implementation",
    "composition",
    "verification-spec",
  ]),
  Candidate: new Set(["implementation", "blocker"]),
  "Target-only": new Set(["intent", "blocker"]),
  "Human-blocked": new Set(["authority", "blocker"]),
};

const source = JSON.parse(await readFile(SOURCE, "utf8"));
const errors = [];
const ids = new Set();

if (source.schemaVersion !== 1)
  errors.push("capability maturity schemaVersion must be 1");
if (!Array.isArray(source.entries) || source.entries.length === 0)
  errors.push("capability maturity entries must be a non-empty array");

for (const entry of source.entries ?? []) {
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(entry.id ?? ""))
    errors.push(`invalid capability id: ${entry.id}`);
  if (ids.has(entry.id)) errors.push(`duplicate capability id: ${entry.id}`);
  ids.add(entry.id);
  if (!VALID_STATUSES.has(entry.status))
    errors.push(`${entry.id}: invalid status ${entry.status}`);
  if (!entry.owner || !entry.name || !entry.summary)
    errors.push(`${entry.id}: name, owner and summary are required`);
  if (!Array.isArray(entry.evidence) || entry.evidence.length === 0)
    errors.push(`${entry.id}: at least one evidence probe is required`);
  const evidenceKinds = new Set(
    (entry.evidence ?? []).map(({ kind }) => kind).filter(Boolean),
  );
  for (const required of REQUIRED_EVIDENCE_KINDS[entry.status] ?? []) {
    if (!evidenceKinds.has(required))
      errors.push(
        `${entry.id}: ${entry.status} requires ${required} evidence`,
      );
  }
  if (
    entry.status === "Human-blocked" &&
    (!Array.isArray(entry.requiredAuthorities) ||
      entry.requiredAuthorities.length === 0)
  )
    errors.push(`${entry.id}: Human-blocked requires human authorities`);

  for (const probe of entry.evidence ?? []) {
    const target = path.resolve(ROOT, probe.path ?? "");
    if (
      !probe.path ||
      path.relative(ROOT, target).startsWith("../") ||
      path.isAbsolute(path.relative(ROOT, target))
    ) {
      errors.push(`${entry.id}: invalid evidence path ${probe.path}`);
      continue;
    }
    try {
      await access(target);
      if (probe.exists === false)
        errors.push(`${entry.id}: expected ${probe.path} to be absent`);
      if (probe.contains || probe.absent) {
        if ((await stat(target)).isDirectory()) {
          errors.push(`${entry.id}: text probe cannot target ${probe.path}`);
          continue;
        }
        const content = await readFile(target, "utf8");
        if (probe.contains && !content.includes(probe.contains))
          errors.push(
            `${entry.id}: ${probe.path} is missing ${JSON.stringify(probe.contains)}`,
          );
        if (probe.absent && content.includes(probe.absent))
          errors.push(
            `${entry.id}: ${probe.path} unexpectedly contains ${JSON.stringify(probe.absent)}`,
          );
      }
    } catch (error) {
      if (error.code === "ENOENT" && probe.exists === false) continue;
      errors.push(`${entry.id}: evidence path is missing: ${probe.path}`);
    }
  }
}

if (errors.length > 0) {
  errors.forEach((error) => process.stderr.write(`- ${error}\n`));
  process.exit(1);
}

const rows = source.entries
  .map(
    (entry) =>
      `| ${entry.name} | ${entry.status} | \`${entry.owner}\` | ${entry.summary} |`,
  )
  .join("\n");
const evidence = source.entries
  .map((entry) => {
    const links = entry.evidence
      .map((probe) => `\`${probe.path}\``)
      .join(", ");
    return `- **${entry.name}:** ${links}`;
  })
  .join("\n");
const rendered = `---
id: customer-assistant-capability-maturity
title: Customer Assistant capability maturity
status: active
owner_role: engineering-lead
scope: cross-system
when_to_read:
  - capability-maturity
  - staging-readiness
tags:
  - customer-chatbot
  - capability-maturity
  - staging
revision: 1
review_date: 2026-08-29
supersedes: []
---

# Customer Assistant capability maturity

> Generated from the curated
> \`customer-assistant-capability-maturity.json\` register. The generator
> requires status-specific implementation, composition, verification-spec,
> blocker or human-authority probes. A verification-spec proves that a
> repository gate exists; observed execution evidence remains attached to the
> owning Work Item and release run. This report does not infer production
> approval.

| Capability | Maturity | Owner | Evidence-based interpretation |
| --- | --- | --- | --- |
${rows}

## Meaning of maturity

- **Implemented:** composed in the active runtime and covered by a repository
  verification specification. The latest observed pass/fail belongs to the
  owning Work Item or immutable release evidence, not this maturity register.
- **Candidate:** substantive implementation exists but one or more acceptance,
  composition or release gates remain.
- **Target-only:** architecture or contract intent exists without an accepted
  runtime consumer.
- **Human-blocked:** technical work cannot replace an explicit human authority
  decision or approved business artifact.

## Evidence probes

${evidence}

The generator validates every referenced path and marker and rejects a status
without its required evidence classes. Human reviewers still own the semantic
accuracy of each maturity classification.
`;

if (process.argv.includes("--write")) {
  await writeFile(OUTPUT, rendered);
  process.stdout.write("Generated Customer Assistant capability maturity.\n");
} else {
  let current = "";
  try {
    current = await readFile(OUTPUT, "utf8");
  } catch {}
  if (current !== rendered) {
    process.stderr.write(
      "Customer Assistant capability maturity is stale; run npm run maturity:generate.\n",
    );
    process.exit(1);
  }
  process.stdout.write("Customer Assistant capability maturity is current.\n");
}
