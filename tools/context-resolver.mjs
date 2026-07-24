#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import path from "node:path";
import { ROOT, resolveContext } from "./lib/governance.mjs";

function parseArguments(argv) {
  const result = { paths: [], signals: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const value = argv[index + 1];
    if (argument === "--path" && value) {
      result.paths.push(value);
      index += 1;
    } else if (argument === "--signals" && value) {
      result.signals.push(...value.split(",").filter(Boolean));
      index += 1;
    } else if (argument === "--request" && value) {
      result.request = value;
      index += 1;
    } else if (argument === "--stage" && value) {
      result.stage = value;
      index += 1;
    } else if (argument === "--work" && value) {
      result.work = value;
      index += 1;
    } else if (argument === "--run" && value) {
      result.runId = value;
      index += 1;
    } else if (argument === "--mode" && value) {
      result.mode = value;
      index += 1;
    } else if (argument === "--uncertainty" && value) {
      result.uncertainty = value;
      index += 1;
    } else if (argument === "--presentation-only") {
      result.presentationOnly = true;
    } else if (argument === "--behavior-change") {
      result.behaviorChange = true;
    } else if (argument === "--irreversible") {
      result.reversible = false;
    } else if (argument === "--safe-default") {
      result.safeDefault = true;
    } else if (argument === "--missing-authority") {
      result.missingAuthority = true;
    } else if (argument === "--multi-story") {
      result.multiStory = true;
    } else if (argument === "--delegated") {
      result.delegated = true;
    } else if (argument === "--bootstrap") {
      result.bootstrap = true;
    } else if (argument === "--previous-context" && value) {
      result.previousContextKey = value;
      index += 1;
    } else if (argument === "--previous-sources" && value) {
      result.previousSourcesFile = value;
      index += 1;
    } else if (argument === "--capsule" && value) {
      result.capsuleFile = value;
      index += 1;
    } else if (argument === "--format" && value) {
      result.format = value;
      index += 1;
    } else if (argument === "--help") {
      result.help = true;
    } else {
      throw new Error(`Unknown or incomplete argument: ${argument}`);
    }
  }
  return result;
}

const input = parseArguments(process.argv.slice(2));
if (input.help) {
  process.stdout.write(`Usage: node tools/context-resolver.mjs [options]\n\n`);
  process.stdout.write(
    `  --path <path>             Repeat for every touched path\n`,
  );
  process.stdout.write(`  --request <text>          Short requested outcome\n`);
  process.stdout.write(
    `  --stage <stage>           triage, delivery, review, resume...\n`,
  );
  process.stdout.write(
    `  --work <VFBIZ-NNNN>       Load canonical work item constraints\n`,
  );
  process.stdout.write(
    `  --run <run-id>             Attach an observed provider run identifier\n`,
  );
  process.stdout.write(
    `  --mode <mode>             Explicit fast/bounded/controlled/discovery/parallel\n`,
  );
  process.stdout.write(
    `  --signals <a,b>           Controlled, discovery or coordination signals\n`,
  );
  process.stdout.write(
    `  --presentation-only       Marks a reversible visual/copy-only change\n`,
  );
  process.stdout.write(
    `  --behavior-change         Marks externally observable behavior\n`,
  );
  process.stdout.write(
    `  --irreversible            Marks the change as difficult to reverse\n`,
  );
  process.stdout.write(
    `  --safe-default            Records non-material ambiguity\n`,
  );
  process.stdout.write(
    `  --missing-authority       Forces stop-the-line for the affected lane\n`,
  );
  process.stdout.write(
    `  --multi-story             Requires a PRD-lite or higher artifact\n`,
  );
  process.stdout.write(
    `  --delegated               Require a work claim for the writer\n`,
  );
  process.stdout.write(
    `  --bootstrap               Emit a self-contained provider-neutral capsule\n`,
  );
  process.stdout.write(
    `  --previous-context <sha>  Emit only sources changed since a cached context\n`,
  );
  process.stdout.write(
    `  --previous-sources <file> Load a path-to-SHA-256 map for resume delta\n`,
  );
  process.stdout.write(
    `  --capsule <file>          Load previous context key/source hashes from a capsule\n`,
  );
  process.stdout.write(
    `  --format <json|markdown>  Bootstrap output format (default: markdown)\n`,
  );
  process.exit(0);
}

if (input.previousSourcesFile) {
  const raw = JSON.parse(
    await readFile(path.resolve(ROOT, input.previousSourcesFile), "utf8"),
  );
  input.previousSourceHashes = sourceHashMap(raw);
}
if (input.capsuleFile) {
  const capsule = JSON.parse(
    await readFile(path.resolve(ROOT, input.capsuleFile), "utf8"),
  );
  input.previousContextKey ??=
    capsule.context_key ?? capsule.contextKey ?? capsule.previous_context_key;
  input.previousSourceHashes = {
    ...(input.previousSourceHashes ?? {}),
    ...sourceHashMap(capsule),
  };
}
delete input.previousSourcesFile;
delete input.capsuleFile;

const result = await resolveContext(input);
if (!input.bootstrap) {
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
} else if ((input.format ?? "markdown") === "json") {
  process.stdout.write(
    `${JSON.stringify(await bootstrapPayload(result), null, 2)}\n`,
  );
} else {
  process.stdout.write(`${renderMarkdown(await bootstrapPayload(result))}\n`);
}

function sourceHashMap(value) {
  if (!value || typeof value !== "object") return {};
  const direct =
    value.source_hashes ?? value.sourceHashes ?? value.previousSourceHashes;
  if (direct && !Array.isArray(direct) && typeof direct === "object") {
    return Object.fromEntries(
      Object.entries(direct).filter(
        ([sourcePath, hash]) =>
          typeof sourcePath === "string" && /^[a-f0-9]{64}$/.test(hash),
      ),
    );
  }
  const revisions =
    value.contextSourceRevisions ??
    value.context_source_revisions ??
    value.sourceRevisions ??
    [];
  return Object.fromEntries(
    revisions
      .map((source) => [
        source.path ?? source.sourceId ?? source.source_id,
        source.sourceHash ?? source.sha256,
      ])
      .filter(
        ([sourcePath, hash]) =>
          typeof sourcePath === "string" && /^[a-f0-9]{64}$/.test(hash),
      ),
  );
}

async function bootstrapPayload(context) {
  const isDelta = Boolean(context.resumeDelta.previousContextKey);
  const changed = new Set(context.resumeDelta.changedSources);
  const instructions = [];
  for (const source of context.instructions.filter(
    ({ path: sourcePath }) => !isDelta || changed.has(sourcePath),
  )) {
    const content = await readFile(path.join(ROOT, source.path), "utf8");
    instructions.push({ ...source, content });
  }
  const roleSource = context.sourceRevisions.find(
    ({ kind }) => kind === "role",
  );
  const role =
    roleSource && (!isDelta || changed.has(roleSource.path))
      ? {
          ...roleSource,
          content: await readFile(path.join(ROOT, roleSource.path), "utf8"),
        }
      : null;
  const skills = [];
  for (const source of context.sourceRevisions.filter(
    ({ kind, path: sourcePath }) =>
      kind === "skill" && (!isDelta || changed.has(sourcePath)),
  )) {
    const content = await readFile(path.join(ROOT, source.path), "utf8");
    skills.push({
      ...source,
      id:
        context.requiredSkills.find((skillId) =>
          source.path.includes(`/${skillId}/SKILL.md`),
        ) ?? path.basename(path.dirname(source.path)),
      content,
    });
  }
  const selectedDocuments = context.documents;
  const documents = selectedDocuments.filter(
    ({ path: sourcePath }) => !isDelta || changed.has(sourcePath),
  );
  return {
    ...context,
    selectedDocuments,
    instructions,
    documents,
    role,
    skills,
  };
}

function renderMarkdown(context) {
  const lines = [
    `# VFBiz agent bootstrap`,
    ``,
    `Context key: \`${context.contextKey}\``,
    `Mode: \`${context.classification.mode}\`; owner team: \`${context.ownership.ownerTeam ?? "unassigned"}\`; accountable role: \`${context.ownership.accountableRole}\`.`,
    ``,
    `## Assignment`,
    ``,
    context.assignment
      ? "```json"
      : "No writer assignment was issued. The lane is `needs-decision`.",
  ];
  if (context.assignment) {
    lines.push(JSON.stringify(context.assignment, null, 2), "```");
  }
  if (context.workItem) {
    lines.push("", "## Work item excerpts", "");
    for (const section of Object.values(context.workItem.sections)) {
      if (!section.excerpt) continue;
      lines.push(
        `### ${section.heading.replace(/^#+\s*/, "")}`,
        "",
        section.excerpt,
        "",
      );
    }
  }
  if (context.role) {
    lines.push(
      "## Canonical role",
      "",
      `Source: \`${context.role.path}\`; SHA-256: \`${context.role.sourceHash}\``,
      "",
      context.role.content.trim(),
      "",
    );
  }
  lines.push("## Instruction chain", "");
  for (const instruction of context.instructions) {
    lines.push(
      `### ${instruction.path}`,
      "",
      `Source SHA-256: \`${instruction.sourceHash}\``,
      "",
      instruction.content.trim(),
      "",
    );
  }
  if (context.documents.length) {
    lines.push("## Selected documentation", "");
    for (const document of context.documents) {
      lines.push(
        `### ${document.path}:${document.selection.startLine}-${document.selection.endLine}`,
        "",
        `Source SHA-256: \`${document.selection.sourceHash}\``,
        "",
        document.selection.excerpt,
        "",
      );
    }
  }
  if (context.skills.length) {
    lines.push("## Selected skills", "");
    for (const skill of context.skills) {
      lines.push(
        `### ${skill.id}`,
        "",
        `Source: \`${skill.path}\`; SHA-256: \`${skill.sourceHash}\``,
        "",
        skill.content.trim(),
        "",
      );
    }
  }
  if (context.resumeDelta.previousContextKey) {
    lines.push(
      "## Resume delta",
      "",
      `Previous context: \`${context.resumeDelta.previousContextKey}\`.`,
      `Unchanged sources omitted: ${context.resumeDelta.unchangedSources.length}.`,
      `Changed sources emitted: ${context.resumeDelta.changedSources.length}.`,
      "",
    );
  }
  lines.push(
    "",
    "## Guardrails",
    "",
    `Claim required: ${context.claimRequired ? "yes" : "no"}.`,
    `Exclusive resources: ${context.exclusiveResources.join(", ") || "none"}.`,
    "Do not recursively read docs or delegate from a worker.",
  );
  return lines.join("\n").trimEnd();
}
