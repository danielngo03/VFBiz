#!/usr/bin/env node
import {
  open,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFrontmatter, renderFrontmatter } from "./lib/frontmatter.mjs";
import { loadOrganization } from "./lib/governance.mjs";
import { assertWorkReviewComplete } from "./lib/agent-control.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ITEMS = path.resolve(
  process.env.VFBIZ_WORK_ITEMS_DIR ?? path.join(ROOT, "docs/work/items"),
);
const WORK_VIEW = path.resolve(
  process.env.VFBIZ_WORK_VIEW ?? path.join(ROOT, "WORK.md"),
);
const STATE_DIR = path.resolve(
  process.env.VFBIZ_WORK_STATE_DIR ?? path.join(ROOT, ".git", "vfbiz-work"),
);
const LOCK_FILE = path.join(STATE_DIR, "work.lock");
const STATUSES = [
  "proposed",
  "ready",
  "active",
  "review",
  "blocked",
  "done",
  "cancelled",
];
const MODES = ["bounded", "controlled", "discovery", "parallel"];
const PRIORITIES = ["P0", "P1", "P2", "P3"];
const TRANSITIONS = {
  proposed: new Set(["ready", "cancelled"]),
  ready: new Set(["active", "cancelled"]),
  active: new Set(["review", "blocked", "cancelled"]),
  review: new Set(["done", "blocked"]),
  blocked: new Set(["active", "review", "cancelled"]),
  done: new Set(),
  cancelled: new Set(),
};

function options(argv) {
  const result = { positional: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (!value.startsWith("--")) result.positional.push(value);
    else if (value === "--write") result.write = true;
    else {
      const key = value
        .slice(2)
        .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
      if (!argv[index + 1] || argv[index + 1].startsWith("--"))
        throw new Error(`${value} requires a value`);
      result[key] = argv[index + 1];
      index += 1;
    }
  }
  return result;
}

function canonicalId(value) {
  const id = String(value ?? "").toUpperCase();
  if (!/^VFBIZ-[0-9]{4}$/.test(id))
    throw new Error(`Invalid work ID ${value}; expected VFBIZ-NNNN`);
  return id;
}

function listOption(value, fallback = []) {
  return value === undefined
    ? fallback
    : value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

async function loadItems() {
  const result = [];
  let names = [];
  try {
    names = await readdir(ITEMS);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  for (const name of names
    .filter((entry) => /^VFBIZ-[0-9]{4}\.md$/.test(entry))
    .sort()) {
    const file = path.join(ITEMS, name);
    const parsed = await readFrontmatter(file);
    result.push({
      file,
      relative: path.relative(ROOT, file).split(path.sep).join("/"),
      ...parsed,
    });
  }
  return result;
}

function markdownSection(body, heading) {
  const lines = body.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === heading);
  if (start < 0) return "";
  const level = heading.match(/^#+/)?.[0].length ?? 1;
  const endOffset = lines.slice(start + 1).findIndex((line) => {
    const match = line.match(/^(#+)\s/);
    return match && match[1].length <= level;
  });
  const end = endOffset < 0 ? lines.length : start + 1 + endOffset;
  return lines
    .slice(start + 1, end)
    .join("\n")
    .trim();
}

function hasConcreteAcceptance(item) {
  const section = markdownSection(item.body, "## Done when");
  return (
    /^\s*[-*]\s+\S/m.test(section) &&
    !/Describe|Acceptance is observed/i.test(section)
  );
}

function observedCheckLines(item) {
  return markdownSection(item.body, "## Evidence")
    .split(/\r?\n/)
    .filter((line) => /^\s*[-*]\s+\[[xX]\]\s+/.test(line));
}

function hasRequiredEvidence(item) {
  const lines = observedCheckLines(item);
  if (lines.length === 0) return false;
  return (item.attributes.required_checks ?? []).every((check) =>
    lines.some(
      (line) =>
        line.toLowerCase().includes(String(check).toLowerCase()) &&
        !/(not run|chưa chạy|placeholder|todo|add evidence)/i.test(line),
    ),
  );
}

function validateItem(item, organization, itemsById) {
  const errors = [];
  const data = item.attributes;
  const required = [
    "id",
    "title",
    "status",
    "mode",
    "priority",
    "owner_team",
    "accountable_role",
    "primary_workspace",
    "affected_workspaces",
    "allowed_paths",
    "depends_on",
    "controlled_signals",
    "exclusive_resources",
    "required_checks",
    "revision",
    "review_date",
  ];
  for (const key of required)
    if (!(key in data)) errors.push(`${item.relative}: missing ${key}`);
  if (!/^VFBIZ-[0-9]{4}$/.test(data.id ?? ""))
    errors.push(`${item.relative}: invalid id`);
  if (!STATUSES.includes(data.status))
    errors.push(`${item.relative}: invalid status ${data.status}`);
  if (!MODES.includes(data.mode))
    errors.push(`${item.relative}: invalid mode ${data.mode}`);
  if (!PRIORITIES.includes(data.priority))
    errors.push(`${item.relative}: invalid priority ${data.priority}`);
  const team = organization.teams.find(({ id }) => id === data.owner_team);
  if (!team)
    errors.push(`${item.relative}: unknown owner_team ${data.owner_team}`);
  if (!organization.humanAuthorities.includes(data.accountable_role))
    errors.push(
      `${item.relative}: unknown accountable_role ${data.accountable_role}`,
    );
  const workspaceIds = new Set(organization.workspaces.map(({ id }) => id));
  if (!workspaceIds.has(data.primary_workspace))
    errors.push(
      `${item.relative}: unknown primary_workspace ${data.primary_workspace}`,
    );
  for (const key of [
    "affected_workspaces",
    "allowed_paths",
    "depends_on",
    "controlled_signals",
    "exclusive_resources",
    "required_checks",
  ]) {
    if (!Array.isArray(data[key]))
      errors.push(`${item.relative}: ${key} must be an array`);
  }
  for (const workspace of data.affected_workspaces ?? [])
    if (!workspaceIds.has(workspace))
      errors.push(`${item.relative}: unknown affected workspace ${workspace}`);
  if (
    Array.isArray(data.affected_workspaces) &&
    !data.affected_workspaces.includes(data.primary_workspace)
  )
    errors.push(
      `${item.relative}: affected_workspaces must include primary_workspace`,
    );
  if (Array.isArray(data.allowed_paths) && data.allowed_paths.length === 0)
    errors.push(`${item.relative}: allowed_paths must not be empty`);
  for (const dependency of data.depends_on ?? []) {
    if (dependency === data.id)
      errors.push(`${item.relative}: work item cannot depend on itself`);
    else if (!itemsById.has(dependency))
      errors.push(`${item.relative}: missing dependency ${dependency}`);
  }
  for (const heading of [
    "# Outcome",
    "## Constraints",
    "## Done when",
    "## Checkpoint",
    "## Evidence",
  ]) {
    if (!item.body.includes(heading))
      errors.push(`${item.relative}: missing heading ${heading}`);
  }
  return errors;
}

function validateReady(item, itemsById) {
  const errors = [];
  if (!hasConcreteAcceptance(item))
    errors.push("Done when must contain concrete acceptance criteria");
  if ((item.attributes.allowed_paths ?? []).length === 0)
    errors.push("allowed_paths must not be empty");
  for (const id of item.attributes.depends_on ?? []) {
    const dependency = itemsById.get(id);
    if (!dependency || dependency.attributes.status !== "done")
      errors.push(`dependency ${id} is not done`);
  }
  return errors;
}

function renderView(items, organization) {
  const rows = items
    .filter(
      ({ attributes }) => !["done", "cancelled"].includes(attributes.status),
    )
    .sort(
      (left, right) =>
        PRIORITIES.indexOf(left.attributes.priority) -
          PRIORITIES.indexOf(right.attributes.priority) ||
        left.attributes.id.localeCompare(right.attributes.id),
    )
    .map(({ attributes, relative }) => {
      const team = organization.teams.find(
        ({ id }) => id === attributes.owner_team,
      );
      const dependency = attributes.depends_on?.length
        ? attributes.depends_on.join(", ")
        : "—";
      const blocker = attributes.status === "blocked" ? "See checkpoint" : "—";
      return `| ${attributes.id} | ${attributes.priority} | ${attributes.status} | ${team?.name ?? attributes.owner_team} | ${attributes.primary_workspace} | ${dependency} | ${blocker} | [${attributes.title}](${relative}) |`;
    });
  return `# Work overview\n\n> Generated by \`npm run work:generate\`. Canonical state lives in \`docs/work/items/\`.\n\n| Work ID | Priority | Status | Owner team | Workspace | Dependencies | Blocker | Work item |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n${rows.join("\n") || "| — | — | — | — | — | — | — | No active work |"}\n`;
}

function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

async function acquireWorkLock() {
  await import("node:fs/promises").then(({ mkdir }) =>
    mkdir(STATE_DIR, { recursive: true }),
  );
  for (let attempt = 0; attempt < 240; attempt += 1) {
    try {
      const handle = await open(LOCK_FILE, "wx", 0o600);
      await handle.writeFile(
        `${JSON.stringify({ pid: process.pid, acquiredAt: new Date().toISOString() })}\n`,
      );
      return handle;
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      try {
        const lock = JSON.parse(await readFile(LOCK_FILE, "utf8"));
        const age = Date.now() - Date.parse(lock.acquiredAt);
        if (!processAlive(Number(lock.pid)) && age > 5_000) {
          await rm(LOCK_FILE, { force: true });
          continue;
        }
      } catch (readError) {
        if (readError.code === "ENOENT") continue;
      }
      await new Promise((resolve) =>
        setTimeout(resolve, 10 + Math.floor(Math.random() * 20)),
      );
    }
  }
  throw new Error("work registry is busy; no state was changed");
}

async function withWorkLock(operation) {
  const lock = await acquireWorkLock();
  try {
    return await operation();
  } finally {
    await lock.close();
    await rm(LOCK_FILE, { force: true });
  }
}

async function atomicWrite(file, content) {
  const temporary = `${file}.${process.pid}.tmp`;
  await writeFile(temporary, content, { mode: 0o644 });
  await rename(temporary, file);
}

function appendEvent(item, status, note) {
  const timestamp = new Date().toISOString();
  item.attributes.status = status;
  item.attributes.revision = Number(item.attributes.revision ?? 0) + 1;
  item.attributes.updated_at = timestamp;
  if (note)
    item.body = `${item.body.trimEnd()}\n\n### ${status} — ${timestamp}\n\n${note}\n`;
}

function assertTransition(item, target) {
  if (!TRANSITIONS[item.attributes.status]?.has(target))
    throw new Error(
      `invalid transition ${item.attributes.status} -> ${target}`,
    );
}

const [command = "list", ...rest] = process.argv.slice(2);
const args = options(rest);
const organization = await loadOrganization();

async function mutate(operation) {
  return withWorkLock(async () => {
    const items = await loadItems();
    const byId = new Map(items.map((item) => [item.attributes.id, item]));
    const result = await operation(items, byId);
    const refreshed = await loadItems();
    await atomicWrite(WORK_VIEW, renderView(refreshed, organization));
    return result;
  });
}

if (command === "check") {
  const items = await loadItems();
  const byId = new Map(items.map((item) => [item.attributes.id, item]));
  const errors = items.flatMap((item) =>
    validateItem(item, organization, byId),
  );
  if (errors.length > 0) {
    errors.forEach((error) => process.stderr.write(`- ${error}\n`));
    process.exit(1);
  }
  process.stdout.write(`Validated ${items.length} WorkItemV2 file(s).\n`);
} else if (command === "list") {
  const view = renderView(await loadItems(), organization);
  if (args.write) {
    await atomicWrite(WORK_VIEW, view);
    process.stdout.write("Generated WORK.md.\n");
  } else process.stdout.write(view);
} else if (command === "show") {
  const id = canonicalId(args.positional[0]);
  const item = (await loadItems()).find(
    ({ attributes }) => attributes.id === id,
  );
  if (!item) throw new Error(`${id} does not exist`);
  process.stdout.write(await readFile(item.file, "utf8"));
} else if (command === "new") {
  const created = await mutate(async (items, byId) => {
    const existingNumbers = items.map(({ attributes }) =>
      Number(attributes.id.slice(6)),
    );
    const id = args.id
      ? canonicalId(args.id)
      : `VFBIZ-${String(Math.max(0, ...existingNumbers) + 1).padStart(4, "0")}`;
    if (byId.has(id)) throw new Error(`${id} already exists`);
    const mode = args.mode ?? "bounded";
    const priority = (args.priority ?? "P2").toUpperCase();
    if (!MODES.includes(mode)) throw new Error(`Invalid mode ${mode}`);
    if (!PRIORITIES.includes(priority))
      throw new Error(`Invalid priority ${priority}`);
    const primaryWorkspace = args.workspace ?? "root";
    const attributes = {
      id,
      title: args.title ?? "Untitled work item",
      status: "proposed",
      mode,
      priority,
      owner_team: args.ownerTeam ?? "agent-platform",
      accountable_role: args.accountableRole ?? "engineering-lead",
      primary_workspace: primaryWorkspace,
      affected_workspaces: listOption(args.affectedWorkspaces, [
        primaryWorkspace,
      ]),
      allowed_paths: listOption(args.allowedPaths),
      depends_on: listOption(args.dependsOn),
      controlled_signals: listOption(args.controlledSignals),
      exclusive_resources: listOption(args.exclusiveResources),
      required_checks: listOption(args.requiredChecks),
      revision: 1,
      review_date: args.reviewDate ?? new Date().toISOString().slice(0, 10),
    };
    const checks = attributes.required_checks.length
      ? attributes.required_checks
          .map((check) => `- [ ] \`${check}\` — add evidence reference`)
          .join("\n")
      : "- [ ] acceptance — add evidence reference";
    const body = `# Outcome\n\nDescribe one measurable outcome.\n\n## Constraints\n\n- None recorded.\n\n## Done when\n\n- Replace this placeholder with observable acceptance.\n\n## Checkpoint\n\n- Exact next action: refine this work item.\n\n## Evidence\n\n${checks}\n`;
    const file = path.join(ITEMS, `${id}.md`);
    const handle = await open(file, "wx", 0o644);
    try {
      await handle.writeFile(renderFrontmatter(attributes, body));
    } finally {
      await handle.close();
    }
    return path.relative(ROOT, file).split(path.sep).join("/");
  });
  process.stdout.write(`${created}\n`);
} else if (
  [
    "ready",
    "start",
    "review",
    "checkpoint",
    "block",
    "done",
    "cancel",
  ].includes(command)
) {
  const output = await mutate(async (_items, byId) => {
    const id = canonicalId(args.positional[0]);
    const item = byId.get(id);
    if (!item) throw new Error(`${id} does not exist`);
    if (command === "checkpoint") {
      if (!["active", "review", "blocked"].includes(item.attributes.status))
        throw new Error(
          `checkpoint is not valid from ${item.attributes.status}`,
        );
      appendEvent(
        item,
        item.attributes.status,
        args.note ??
          "Checkpoint recorded; add observed state and one exact next action.",
      );
    } else {
      const target = {
        ready: "ready",
        start: "active",
        review: "review",
        block: "blocked",
        done: "done",
        cancel: "cancelled",
      }[command];
      assertTransition(item, target);
      if (target === "ready") {
        const errors = validateReady(item, byId);
        if (errors.length)
          throw new Error(`work item is not ready: ${errors.join("; ")}`);
      }
      if (target === "done") {
        const dependencyErrors = validateReady(item, byId).filter((error) =>
          error.startsWith("dependency"),
        );
        if (dependencyErrors.length)
          throw new Error(
            `work item cannot complete: ${dependencyErrors.join("; ")}`,
          );
        if (!hasRequiredEvidence(item))
          throw new Error(
            "work item cannot complete without checked evidence for every required check",
          );
        await assertWorkReviewComplete(item);
      }
      if (target === "blocked" && !args.note)
        throw new Error("blocking condition must be recorded with --note");
      appendEvent(item, target, args.note);
    }
    await atomicWrite(item.file, renderFrontmatter(item.attributes, item.body));
    return `${item.attributes.id} -> ${item.attributes.status}`;
  });
  process.stdout.write(`${output}\n`);
} else {
  throw new Error(`Unknown command ${command}`);
}
