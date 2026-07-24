#!/usr/bin/env node
import { spawn } from "node:child_process";
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { renderFrontmatter } from "./lib/frontmatter.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const temporary = await mkdtemp(
  path.join(os.tmpdir(), "vfbiz-work-management-"),
);
const items = path.join(temporary, "items");
const state = path.join(temporary, "state");
const view = path.join(temporary, "WORK.md");
const environment = {
  ...process.env,
  VFBIZ_WORK_ITEMS_DIR: items,
  VFBIZ_WORK_STATE_DIR: state,
  VFBIZ_WORK_VIEW: view,
};
let failures = 0;

function assert(condition, message) {
  if (!condition) {
    failures += 1;
    process.stderr.write(`- ${message}\n`);
  }
}

function run(argumentsList) {
  return new Promise((resolve) => {
    const child = spawn(
      process.execPath,
      ["tools/work.mjs", ...argumentsList],
      {
        cwd: ROOT,
        env: environment,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("close", (status) => resolve({ status, stdout, stderr }));
  });
}

function fixture(id, options = {}) {
  const checks = options.checked
    ? "- [x] `governance` — observed:test-governance"
    : "- [ ] `governance` — add evidence reference";
  return renderFrontmatter(
    {
      id,
      title: `Test ${id}`,
      status: options.status ?? "proposed",
      mode: "bounded",
      priority: "P2",
      owner_team: "agent-platform",
      accountable_role: "engineering-lead",
      primary_workspace: "root",
      affected_workspaces: ["root"],
      allowed_paths: ["tools"],
      depends_on: options.dependsOn ?? [],
      controlled_signals: [],
      exclusive_resources: [],
      required_checks: ["governance"],
      revision: 1,
      review_date: "2026-08-23",
    },
    `# Outcome\n\nVerify the work registry.\n\n## Constraints\n\n- Isolated temporary registry.\n\n## Done when\n\n- The observed transition is deterministic.\n\n## Checkpoint\n\n- Exact next action: run the next transition.\n\n## Evidence\n\n${checks}\n`,
  );
}

try {
  await mkdir(items, { recursive: true });
  const concurrent = await Promise.all(
    Array.from({ length: 20 }, (_, index) =>
      run([
        "new",
        "--title",
        `Concurrent ${index + 1}`,
        "--allowed-paths",
        "tools",
        "--required-checks",
        "governance",
      ]),
    ),
  );
  assert(
    concurrent.every(({ status }) => status === 0),
    "20 concurrent allocations must all succeed",
  );
  const allocated = (await readdir(items)).filter((name) =>
    /^VFBIZ-[0-9]{4}\.md$/.test(name),
  );
  assert(
    allocated.length === 20 && new Set(allocated).size === 20,
    "concurrent allocation must create 20 unique IDs",
  );

  await writeFile(path.join(items, "VFBIZ-0101.md"), fixture("VFBIZ-0101"));
  await writeFile(
    path.join(items, "VFBIZ-0102.md"),
    fixture("VFBIZ-0102", { dependsOn: ["VFBIZ-0101"] }),
  );
  const dependencyBlocked = await run(["ready", "VFBIZ-0102"]);
  assert(
    dependencyBlocked.status !== 0 &&
      /dependency VFBIZ-0101 is not done/.test(dependencyBlocked.stderr),
    "unfinished dependency must block ready",
  );

  assert(
    (await run(["ready", "VFBIZ-0101"])).status === 0,
    "proposed must transition to ready",
  );
  assert(
    (await run(["start", "VFBIZ-0101"])).status === 0,
    "ready must transition to active",
  );
  const duplicateStart = await run(["start", "VFBIZ-0101"]);
  assert(
    duplicateStart.status !== 0 &&
      /invalid transition/.test(duplicateStart.stderr),
    "invalid state transition must be rejected",
  );
  assert(
    (await run(["review", "VFBIZ-0101"])).status === 0,
    "active must transition to review",
  );
  const missingEvidence = await run(["done", "VFBIZ-0101"]);
  assert(
    missingEvidence.status !== 0 &&
      /checked evidence/.test(missingEvidence.stderr),
    "done must require checked evidence",
  );

  const dependencyContent = await readFile(
    path.join(items, "VFBIZ-0101.md"),
    "utf8",
  );
  await writeFile(
    path.join(items, "VFBIZ-0101.md"),
    dependencyContent.replace(
      "- [ ] `governance` — add evidence reference",
      "- [x] `governance` — observed:test-governance",
    ),
  );
  assert(
    (await run(["done", "VFBIZ-0101"])).status === 0,
    "review with evidence must transition to done",
  );
  assert(
    (await run(["ready", "VFBIZ-0102"])).status === 0,
    "completed dependency must unblock ready",
  );

  await mkdir(state, { recursive: true });
  await writeFile(
    path.join(state, "work.lock"),
    JSON.stringify({ pid: 99999999, acquiredAt: "2000-01-01T00:00:00.000Z" }),
  );
  const staleRecovery = await run([
    "new",
    "--id",
    "VFBIZ-0200",
    "--allowed-paths",
    "tools",
  ]);
  assert(
    staleRecovery.status === 0,
    "stale work lock must be recovered safely",
  );
  assert(
    (await run(["check"])).status === 0,
    "temporary WorkItemV2 registry must validate",
  );
} finally {
  await rm(temporary, { recursive: true, force: true });
}

if (failures > 0) process.exit(1);
process.stdout.write(
  "Work management checks passed: atomic IDs, transitions, dependencies, evidence and stale-lock recovery.\n",
);
