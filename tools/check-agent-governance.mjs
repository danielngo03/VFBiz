#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import {
  lstat,
  mkdtemp,
  readFile,
  readdir,
  readlink,
  realpath,
  rm,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { readFrontmatter } from "./lib/frontmatter.mjs";
import { resolveContext } from "./lib/governance.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const failures = [];
const fail = (message) => failures.push(message);

async function json(relative) {
  try {
    return JSON.parse(await readFile(path.join(ROOT, relative), "utf8"));
  } catch (error) {
    fail(`${relative}: ${error.message}`);
    return null;
  }
}

async function exists(file) {
  try {
    await lstat(file);
    return true;
  } catch {
    return false;
  }
}
function same(actual, expected) {
  return (
    actual.length === expected.length &&
    [...actual]
      .sort()
      .every((value, index) => value === [...expected].sort()[index])
  );
}

async function walk(directory, predicate = () => true) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if ([".git", "node_modules", "vendor", ".venv"].includes(entry.name))
      continue;
    const absolute = path.join(directory, entry.name);
    const relative = path.relative(ROOT, absolute).split(path.sep).join("/");
    if (
      relative === "drupal/web/core" ||
      relative.startsWith("drupal/web/core/")
    )
      continue;
    if (entry.isDirectory()) result.push(...(await walk(absolute, predicate)));
    else if (predicate(absolute)) result.push(absolute);
  }
  return result;
}

async function validateInstructions(organization) {
  const agentFiles = await walk(
    ROOT,
    (file) => path.basename(file) === "AGENTS.md",
  );
  const byRelative = new Map();
  for (const file of agentFiles) {
    const content = await readFile(file, "utf8");
    const relative = path.relative(ROOT, file).split(path.sep).join("/");
    byRelative.set(relative, Buffer.byteLength(content));
    const root = relative === "AGENTS.md";
    const maxLines = root ? 120 : 80;
    const maxBytes = root ? 8192 : 4096;
    const lines = content.split(/\r?\n/).length;
    if (lines > maxLines)
      fail(`${relative}: ${lines} lines exceeds ${maxLines}`);
    if (Buffer.byteLength(content) > maxBytes)
      fail(`${relative}: exceeds ${maxBytes} bytes`);
  }
  for (const workspace of organization.workspaces.filter(
    ({ id }) => id !== "root",
  )) {
    const segments = workspace.path.split("/");
    const chain = ["AGENTS.md"];
    for (let depth = 1; depth <= segments.length; depth += 1) {
      const candidate = `${segments.slice(0, depth).join("/")}/AGENTS.md`;
      if (byRelative.has(candidate)) chain.push(candidate);
    }
    const bytes = chain.reduce(
      (sum, file) => sum + (byRelative.get(file) ?? 0),
      0,
    );
    if (bytes > 32768)
      fail(`${workspace.id}: instruction chain exceeds 32 KiB`);
    if (bytes > 16384)
      fail(`${workspace.id}: instruction chain exceeds 16 KiB target`);
  }
  for (const relative of byRelative.keys()) {
    if (relative === "AGENTS.md") continue;
    const segments = relative.split("/").slice(0, -1);
    const chain = ["AGENTS.md"];
    for (let depth = 1; depth <= segments.length; depth += 1) {
      const candidate = `${segments.slice(0, depth).join("/")}/AGENTS.md`;
      if (byRelative.has(candidate)) chain.push(candidate);
    }
    const bytes = chain.reduce(
      (sum, file) => sum + (byRelative.get(file) ?? 0),
      0,
    );
    if (bytes > 32768) fail(`${relative}: instruction chain exceeds 32 KiB`);
    if (bytes > 16384)
      fail(`${relative}: instruction chain exceeds 16 KiB target`);
  }
  for (const file of await walk(
    ROOT,
    (candidate) => path.basename(candidate) === "CLAUDE.md",
  )) {
    const content = await readFile(file, "utf8");
    const relative = path.relative(ROOT, file).split(path.sep).join("/");
    if (!content.includes("@AGENTS.md"))
      fail(`${relative}: must import @AGENTS.md`);
    if (content.split(/\r?\n/).length > 30)
      fail(`${relative}: provider adapter is too long`);
  }
}

async function validateRolesAndAdapters(organization) {
  const ids = organization.roles.map(({ id }) => id);
  const workerIds = ids.filter((id) => id !== "orchestrator");
  const canonical = (await readdir(path.join(ROOT, ".agents/roles")))
    .filter((name) => name.endsWith(".md"))
    .map((name) => name.slice(0, -3));
  if (!same(ids, canonical))
    fail(`canonical role files differ from organization roles`);
  for (const [directory, extension] of [
    [".codex/agents", ".toml"],
    [".claude/agents", ".md"],
    [".gemini/agents", ".md"],
  ]) {
    const present = (await readdir(path.join(ROOT, directory)))
      .filter((name) => name.endsWith(extension))
      .map((name) => name.slice(0, -extension.length));
    if (!same(workerIds, present))
      fail(
        `${directory}: provider worker adapters differ from canonical roles`,
      );
    for (const id of present) {
      const content = await readFile(
        path.join(ROOT, directory, `${id}${extension}`),
        "utf8",
      );
      if (!content.includes(`.agents/roles/${id}.md`))
        fail(
          `${directory}/${id}${extension}: canonical role reference missing`,
        );
      const canonicalRole = organization.roles.find((role) => role.id === id);
      if (
        canonicalRole?.mode === "read-only" &&
        ((directory === ".claude/agents" && /\bBash\b/.test(content)) ||
          (directory === ".gemini/agents" &&
            /\brun_shell_command\b/.test(content)))
      ) {
        fail(
          `${directory}/${id}${extension}: read-only adapter has unrestricted shell`,
        );
      }
    }
  }
  const gemini = await json(".gemini/settings.json");
  if (
    JSON.stringify(gemini?.context?.fileName) !== JSON.stringify(["AGENTS.md"])
  )
    fail(".gemini/settings.json: context.fileName must be AGENTS.md");
  if (gemini?.context?.includeDirectoryTree !== false)
    fail(".gemini/settings.json: includeDirectoryTree must be false");
  const codex = await readFile(path.join(ROOT, ".codex/config.toml"), "utf8");
  if (!/max_concurrent_threads_per_session\s*=\s*3/.test(codex))
    fail(".codex/config.toml: expected the documented three-thread cap");
  if (/max_threads|max_depth/.test(codex))
    fail(".codex/config.toml: legacy or undocumented agent keys remain");
  const codexHooks = await json(".codex/hooks.json");
  for (const event of ["PreToolUse", "PostToolUse", "PreCompact"]) {
    if (
      !Array.isArray(codexHooks?.hooks?.[event]) ||
      codexHooks.hooks[event].length === 0
    )
      fail(`.codex/hooks.json: missing ${event}`);
  }
}

async function validateContextHardening() {
  const visual = await resolveContext({
    request: "Change the login button color and copy",
    paths: ["apps/customer-portal/src/app/page.tsx"],
    presentationOnly: true,
  });
  if (visual.classification.mode !== "fast")
    fail("visual login copy task was not classified fast");
  if (
    visual.signals.some((signal) =>
      ["authentication", "customer-bff", "customer-data"].includes(signal),
    )
  )
    fail("visual login copy task inherited controlled auth signals");
  if (visual.documents.length !== 0)
    fail("visual login copy task loaded documentation");
  if (!visual.signals.includes("design-system"))
    fail("visual login copy task did not retain its design-system signal");

  const journey = await resolveContext({
    request: "Improve the customer journey navigation",
    paths: ["apps/customer-portal/src/app/account/page.tsx"],
    behaviorChange: true,
  });
  if (
    journey.classification.mode !== "bounded" ||
    !journey.signals.includes("customer-journey") ||
    journey.ownership.ownerTeam !== "customer-web-experience" ||
    !journey.reviewProfiles.includes("experience")
  )
    fail("customer journey did not route to focused experience review");
  const journeyDocument = journey.documents.find(
    ({ id }) => id === "customer-portal-experience-accessibility",
  );
  if (journeyDocument?.selection.heading !== "## Journey states")
    fail("customer journey did not use its exact documentation anchor");

  const privacy = await resolveContext({
    request: "Implement the customer privacy data-request form",
    paths: ["apps/customer-portal/src/features/privacy/data-request-form.tsx"],
  });
  if (
    !privacy.signals.includes("customer-privacy") ||
    privacy.ownership.ownerTeam !== "customer-web-experience" ||
    !privacy.reviewProfiles.includes("privacy")
  )
    fail("customer privacy path did not route to the privacy review profile");

  const auth = await resolveContext({
    request: "Rotate the customer refresh token",
    paths: [
      "apps/customer-portal/src/platform/session/redis-token-vault.ts",
    ],
  });
  if (auth.classification.mode !== "controlled")
    fail("customer token-vault path was not classified controlled");
  if (
    auth.executionState !== "needs-decision" ||
    auth.writerAuthorized ||
    auth.assignment !== null
  )
    fail("controlled task without a work item received a writer assignment");
  for (const role of [
    "implementer",
    "reviewer-verifier",
    "risk-reviewer",
  ])
    if (!auth.recommendedRoles.includes(role))
      fail(`controlled topology is missing ${role}`);
  if (!auth.reviewProfiles.includes("security"))
    fail("customer token-vault task is missing the security review profile");

  const parallel = await resolveContext({
    request: "Coordinate two disjoint portal and API lanes",
    paths: [
      "apps/customer-portal/src/app/page.tsx",
      "backend/api/src/modules/customer",
    ],
    mode: "parallel",
  });
  if (
    parallel.executionState !== "needs-decision" ||
    parallel.writerAuthorized ||
    parallel.assignment !== null
  )
    fail("parallel task without a work item received a writer assignment");

  const controlled = await resolveContext({
    request: "Complete customer account and privacy journeys",
    paths: [
      "apps/customer-portal/src/platform/api/customer-account/profile-gateway.ts",
    ],
    work: "VFBIZ-0070",
  });
  if (!controlled.assignment)
    fail("ready controlled work item did not receive an assignment");
  else if (
    JSON.stringify(controlled.assignment.review_profiles) !==
    JSON.stringify(controlled.reviewProfiles)
  )
    fail("assignment did not carry focused review profiles");

  const bootstrap = JSON.parse(
    execFileSync(
      process.execPath,
      [
        "tools/context-resolver.mjs",
        "--path",
        "apps/customer-portal/src/app/page.tsx",
        "--request",
        "Improve the account landing content",
        "--bootstrap",
        "--format",
        "json",
      ],
      { cwd: ROOT, encoding: "utf8" },
    ),
  );
  if (!bootstrap.role?.content.startsWith("# "))
    fail("generic bootstrap did not embed the canonical role body");
  if (
    bootstrap.skills.length === 0 ||
    bootstrap.skills.length > 2 ||
    bootstrap.skills.some(({ content }) => !content.includes("---"))
  )
    fail("generic bootstrap did not embed at most two canonical skill bodies");

  const resumed = JSON.parse(
    execFileSync(
      process.execPath,
      [
        "tools/context-resolver.mjs",
        "--path",
        "apps/customer-portal/src/app/page.tsx",
        "--request",
        "Improve the account landing content",
        "--stage",
        "resume",
        "--previous-context",
        bootstrap.contextKey,
        "--bootstrap",
        "--format",
        "json",
      ],
      { cwd: ROOT, encoding: "utf8" },
    ),
  );
  if (
    resumed.instructions.length !== 0 ||
    resumed.documents.length !== 0 ||
    resumed.role !== null ||
    resumed.skills.length > 1 ||
    resumed.resumeDelta.unchangedSources.length === 0
  )
    fail("resume bootstrap re-emitted unchanged source bodies");
}

async function validateCoordinationLifecycle() {
  const stateRoot = await mkdtemp(
    path.join(tmpdir(), "vfbiz-coordination-test-"),
  );
  const env = { ...process.env, VFBIZ_AGENT_STATE_DIR: stateRoot };
  try {
    const created = JSON.parse(
      execFileSync(
        process.execPath,
        [
          "tools/agent-coordinate.mjs",
          "create",
          "--work-item-key",
          "VFBIZ-0068",
          "--requesting-team",
          "customer-web-experience",
          "--owning-team",
          "api-foundation",
          "--shared-outcome",
          "Keep the customer contract aligned",
          "--interface-or-dependency",
          "Customer profile API",
          "--decision-or-artifact-needed",
          "Reviewed contract response",
          "--required-by",
          "2026-07-25",
          "--default-if-not-blocking",
          "Keep the current additive response",
        ],
        { cwd: ROOT, encoding: "utf8", env },
      ),
    );
    const responded = JSON.parse(
      execFileSync(
        process.execPath,
        [
          "tools/agent-coordinate.mjs",
          "respond",
          "--coordination-id",
          created.coordinationId,
          "--responder-team",
          "api-foundation",
          "--response",
          "The additive response is accepted",
          "--evidence",
          "contracts/openapi/public-v1.yaml",
        ],
        { cwd: ROOT, encoding: "utf8", env },
      ),
    );
    const closed = JSON.parse(
      execFileSync(
        process.execPath,
        [
          "tools/agent-coordinate.mjs",
          "close",
          "--coordination-id",
          created.coordinationId,
          "--closed-by",
          "customer-web-experience",
          "--resolution",
          "Portal consumes the accepted additive response",
        ],
        { cwd: ROOT, encoding: "utf8", env },
      ),
    );
    if (
      created.state !== "open" ||
      responded.state !== "responded" ||
      closed.state !== "closed"
    )
      fail("coordination create/respond/close lifecycle is incomplete");
  } finally {
    await rm(stateRoot, { recursive: true, force: true });
  }
}

async function skillIds(root) {
  if (!(await exists(root))) return [];
  const result = [];
  for (const entry of await readdir(root, { withFileTypes: true })) {
    if (
      entry.isDirectory() &&
      (await exists(path.join(root, entry.name, "SKILL.md")))
    )
      result.push(entry.name);
  }
  return result.sort();
}

async function validateSkills(organization) {
  const roots = [
    { path: ".agents/skills", expected: organization.canonicalSkills },
    {
      path: "backend/api/.agents/skills",
      expected: ["evolve-backend-capability", "validate-trip-release"],
    },
    {
      path: "backend/ai/.agents/skills",
      expected: [
        "generate-synthetic-dataset",
        "onboard-dataset",
        "register-ai-tool",
        "validate-ai-release",
      ],
    },
  ];
  for (const item of roots) {
    const base = path.join(ROOT, item.path);
    const ids = await skillIds(base);
    for (const entry of await readdir(base, { withFileTypes: true })) {
      if (
        entry.isDirectory() &&
        !(await exists(path.join(base, entry.name, "SKILL.md")))
      ) {
        fail(`${item.path}/${entry.name}: skill directory is missing SKILL.md`);
      }
    }
    if (!same(ids, item.expected))
      fail(
        `${item.path}: expected ${item.expected.join(", ")}, found ${ids.join(", ")}`,
      );
    for (const id of ids) {
      const file = path.join(base, id, "SKILL.md");
      const parsed = await readFrontmatter(file);
      if (parsed.attributes.name !== id)
        fail(`${item.path}/${id}: frontmatter name mismatch`);
      if (!parsed.attributes.description)
        fail(`${item.path}/${id}: description missing`);
      if ((await readFile(file, "utf8")).split(/\r?\n/).length > 200)
        fail(`${item.path}/${id}: SKILL.md exceeds 200 lines`);
      const openAiMetadata = path.join(base, id, "agents", "openai.yaml");
      if (!(await exists(openAiMetadata)))
        fail(`${item.path}/${id}: agents/openai.yaml is missing`);
    }
  }
  for (const required of [
    "backend/ai/.agents/skills/onboard-dataset/references/source-gate.md",
    "backend/ai/.agents/skills/onboard-dataset/scripts/validate_source_entry.py",
    "backend/ai/.agents/skills/generate-synthetic-dataset/references/generation-contract.md",
    "backend/ai/.agents/skills/generate-synthetic-dataset/references/quality-gates.md",
    "backend/ai/.agents/skills/generate-synthetic-dataset/scripts/validate_candidate.py",
    "backend/ai/.agents/skills/generate-synthetic-dataset/scripts/detect_near_duplicates.py",
    "backend/ai/.agents/skills/generate-synthetic-dataset/scripts/build_manifest.py",
    "backend/ai/tests/skills/test_dataset_skill_scripts.py",
  ])
    if (!(await exists(path.join(ROOT, required))))
      fail(`${required}: required dataset workflow artifact is missing`);
  for (const item of [
    [".claude/skills", "../.agents/skills"],
    ["backend/api/.claude/skills", "../.agents/skills"],
    ["backend/ai/.claude/skills", "../.agents/skills"],
  ]) {
    const link = path.join(ROOT, item[0]);
    if (!(await exists(link)) || !(await lstat(link)).isSymbolicLink())
      fail(`${item[0]}: missing skill symlink`);
    else if ((await readlink(link)) !== item[1])
      fail(`${item[0]}: expected ${item[1]}`);
  }
}

async function validateScenarios(scenarios) {
  if (scenarios?.version !== 4) {
    fail("tests/governance/scenarios.json: expected version 4");
    return;
  }
  if (
    !same(scenarios.providers ?? [], ["codex", "claude", "gemini", "generic"])
  )
    fail("scenario providers differ");
  if ((scenarios.scenarios ?? []).length < 16)
    fail("enterprise routing suite must contain at least 16 scenarios");
  for (const scenario of scenarios.scenarios ?? []) {
    for (const scenarioPath of scenario.input?.paths ?? []) {
      if (
        !(await exists(path.join(ROOT, scenarioPath))) &&
        !(scenario.futurePaths ?? []).includes(scenarioPath)
      ) {
        fail(
          `${scenario.id}: scenario path does not exist and is not declared future: ${scenarioPath}`,
        );
      }
    }
    const context = await resolveContext(scenario.input);
    const expected = scenario.expected;
    if (context.classification.mode !== expected.mode)
      fail(
        `${scenario.id}: mode ${context.classification.mode}, expected ${expected.mode}`,
      );
    if (!same(context.workspaces, expected.workspaces))
      fail(
        `${scenario.id}: workspaces ${context.workspaces}, expected ${expected.workspaces}`,
      );
    if (context.claimRequired !== expected.claimRequired)
      fail(`${scenario.id}: claimRequired mismatch`);
    if (
      context.documents.length > expected.maxDocs ||
      context.documents.length > context.budgets.maxDocs
    )
      fail(`${scenario.id}: document budget exceeded`);
    if (!same(context.requiredSkills, expected.skills))
      fail(
        `${scenario.id}: skills ${context.requiredSkills}, expected ${expected.skills}`,
      );
    if (
      Object.hasOwn(expected, "ownerTeam") &&
      context.ownership.ownerTeam !== expected.ownerTeam
    )
      fail(
        `${scenario.id}: owner team ${context.ownership.ownerTeam}, expected ${expected.ownerTeam}`,
      );
    if (
      Object.hasOwn(expected, "department") &&
      context.ownership.ownerDepartment !== expected.department
    )
      fail(
        `${scenario.id}: department ${context.ownership.ownerDepartment}, expected ${expected.department}`,
      );
    if (
      expected.authorities &&
      !same(context.requiredAuthorities, expected.authorities)
    )
      fail(`${scenario.id}: authorities mismatch`);
    if (
      expected.resources &&
      !same(context.exclusiveResources, expected.resources)
    )
      fail(`${scenario.id}: exclusive resources mismatch`);
    if (expected.roles && !same(context.recommendedRoles, expected.roles))
      fail(`${scenario.id}: recommended roles mismatch`);
    if (
      expected.reviewers &&
      !same(context.requiredReviewers, expected.reviewers)
    )
      fail(`${scenario.id}: required reviewers mismatch`);
    if (
      expected.coordinationTeams &&
      !same(context.ownership.coordinationTeams, expected.coordinationTeams)
    )
      fail(`${scenario.id}: coordination teams mismatch`);
    if (
      Object.hasOwn(expected, "stopped") &&
      context.stopConditions.length > 0 !== expected.stopped
    )
      fail(`${scenario.id}: stop condition mismatch`);
    if (
      Object.hasOwn(expected, "executionState") &&
      context.executionState !== expected.executionState
    )
      fail(`${scenario.id}: execution state mismatch`);
    if (
      Object.hasOwn(expected, "writerAuthorized") &&
      context.writerAuthorized !== expected.writerAuthorized
    )
      fail(`${scenario.id}: writer authorization mismatch`);
    if (
      expected.reviewProfiles &&
      !same(context.reviewProfiles, expected.reviewProfiles)
    )
      fail(`${scenario.id}: review profiles mismatch`);
    for (const signal of expected.signals ?? [])
      if (!context.signals.includes(signal))
        fail(`${scenario.id}: required signal ${signal} was not selected`);
    for (const signal of expected.excludedSignals ?? [])
      if (context.signals.includes(signal))
        fail(`${scenario.id}: excluded signal ${signal} was selected`);
    const selectedDocumentIds = context.documents.map(({ id }) => id);
    for (const document of expected.documents ?? [])
      if (!selectedDocumentIds.includes(document))
        fail(`${scenario.id}: required document ${document} was not selected`);
    for (const document of expected.excludedDocuments ?? [])
      if (selectedDocumentIds.includes(document))
        fail(`${scenario.id}: excluded document ${document} was selected`);
    for (const [documentId, heading] of Object.entries(
      expected.documentHeadings ?? {},
    )) {
      const selected = context.documents.find(({ id }) => id === documentId);
      if (selected?.selection.heading !== heading)
        fail(
          `${scenario.id}: ${documentId} selected ${selected?.selection.heading ?? "nothing"}, expected ${heading}`,
        );
    }
    const selectedInstructions = context.instructions.map(
      ({ path: value }) => value,
    );
    for (const instruction of expected.instructions ?? [])
      if (!selectedInstructions.includes(instruction))
        fail(`${scenario.id}: instruction ${instruction} was not selected`);
    const base = JSON.stringify({
      classification: context.classification,
      workspaces: context.workspaces,
      signals: context.signals,
      skills: context.requiredSkills,
      documents: context.documents,
      claim: context.claimRequired,
    });
    for (const provider of scenarios.providers) {
      const repeated = await resolveContext({ ...scenario.input, provider });
      const comparison = JSON.stringify({
        classification: repeated.classification,
        workspaces: repeated.workspaces,
        signals: repeated.signals,
        skills: repeated.requiredSkills,
        documents: repeated.documents,
        claim: repeated.claimRequired,
      });
      if (comparison !== base)
        fail(`${scenario.id}: routing differs for provider ${provider}`);
    }
  }
}

async function validateSchemas(organization) {
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  const organizationSchema = await json(
    "contracts/governance/organization.schema.json",
  );
  const validateOrganization = ajv.compile(organizationSchema);
  if (!validateOrganization(organization))
    fail(`organization schema: ${ajv.errorsText(validateOrganization.errors)}`);
  const workSchema = await json("contracts/governance/work-item.schema.json");
  const validateWork = ajv.compile(workSchema);
  for (const file of await walk(
    path.join(ROOT, "docs/work/items"),
    (candidate) => /^VFBIZ-[0-9]{4}\.md$/.test(path.basename(candidate)),
  )) {
    const parsed = await readFrontmatter(file);
    if (!validateWork(parsed.attributes))
      fail(
        `${path.relative(ROOT, file)}: ${ajv.errorsText(validateWork.errors)}`,
      );
  }
  const aiSchemaFiles = [
    "source-register.schema.json",
    "dataset-card.schema.json",
    "dataset-manifest.schema.json",
    "dataset-example.schema.json",
    "generation-job.schema.json",
    "evaluation-case.schema.json",
    "ai-release-manifest.schema.json",
  ];
  const aiValidators = new Map();
  for (const name of aiSchemaFiles) {
    const schema = await json(`contracts/ai/${name}`);
    if (schema) aiValidators.set(name, ajv.compile(schema));
  }
  const sourceCandidates = await json(
    "backend/ai/dataset-specs/public-source-candidates.json",
  );
  const validateSource = aiValidators.get("source-register.schema.json");
  const sourceSemanticErrors = (entry) => {
    const proposed = new Set(entry?.proposed_purposes ?? []);
    const approved = entry?.approved_purposes ?? [];
    return approved.every((purpose) => proposed.has(purpose))
      ? []
      : ["approved_purposes must be a subset of proposed_purposes"];
  };
  if (!Array.isArray(sourceCandidates))
    fail("public-source-candidates.json: expected an array");
  else if (validateSource)
    for (const candidate of sourceCandidates)
      if (!validateSource(candidate))
        fail(
          `public source ${candidate?.source_id ?? "unknown"}: ${ajv.errorsText(validateSource.errors)}`,
        );
      else if (sourceSemanticErrors(candidate).length)
        fail(
          `public source ${candidate?.source_id ?? "unknown"}: ${sourceSemanticErrors(candidate).join("; ")}`,
        );
  if (validateSource) {
    const approvedSource = {
      source_id: "approved-source-contract-test",
      version: "1",
      title: "Approved source contract test",
      status: "approved",
      source_type: "synthetic",
      locator: "https://example.invalid/source",
      source_revision: "fixture-1",
      checksum_sha256: "a".repeat(64),
      proposed_purposes: ["knowledge"],
      approved_purposes: ["knowledge"],
      acl_namespaces: ["public_customer:customer-support:vi-VN"],
      classification: "public",
      owner_role: "data-owner",
      custodian_role: "data-steward",
      rights: {
        license_id: "internal-synthetic",
        commercial_use: "permitted",
        derivatives: "permitted",
        redistribution: "prohibited",
        access_conditions: "Synthetic contract fixture only.",
        evidence_urls: ["https://example.invalid/rights"],
        legal_review: "approved",
      },
      retention: {
        policy_id: "contract-test",
        duration_days: 1,
      },
      deletion_method: "Delete the synthetic fixture.",
      approval_evidence: ["DATA-APPROVAL-TEST", "LEGAL-APPROVAL-TEST"],
      review_date: "2026-08-23",
    };
    if (!validateSource(approvedSource))
      fail(
        `approved Source Register contract fixture: ${ajv.errorsText(validateSource.errors)}`,
      );
    if (sourceSemanticErrors(approvedSource).length)
      fail(
        `approved Source Register semantic fixture: ${sourceSemanticErrors(approvedSource).join("; ")}`,
      );
    const missingApprovedBoundary = { ...approvedSource };
    delete missingApprovedBoundary.approved_purposes;
    delete missingApprovedBoundary.acl_namespaces;
    delete missingApprovedBoundary.custodian_role;
    if (validateSource(missingApprovedBoundary))
      fail(
        "approved Source Register entry without purpose, ACL and custodian was accepted",
      );
    const approvedOutsideProposal = {
      ...approvedSource,
      approved_purposes: ["red-team"],
    };
    if (!validateSource(approvedOutsideProposal))
      fail(
        `Source Register subset fixture should pass structure before semantic validation: ${ajv.errorsText(validateSource.errors)}`,
      );
    if (sourceSemanticErrors(approvedOutsideProposal).length === 0)
      fail(
        "Source Register semantic validator accepted an approved purpose outside the proposal",
      );
  }
  const validateExample = aiValidators.get("dataset-example.schema.json");
  for (const [fixture, shouldPass] of [
    ["backend/ai/tests/fixtures/datasets/valid-candidate.jsonl", true],
    ["backend/ai/tests/fixtures/datasets/invalid-candidate.jsonl", false],
  ]) {
    const records = (await readFile(path.join(ROOT, fixture), "utf8"))
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line));
    const observed = records.every((record) => validateExample?.(record));
    if (observed !== shouldPass)
      fail(`${fixture}: schema scenario expected pass=${shouldPass}`);
  }
  for (const file of await walk(
    path.join(ROOT, "backend/ai"),
    (candidate) =>
      candidate.includes("/dataset-specs/") ||
      candidate.includes("/tests/fixtures/datasets/"),
  )) {
    const relative = path.relative(ROOT, file).split(path.sep).join("/");
    const extension = path.extname(file).toLowerCase();
    if (
      [
        ".parquet",
        ".zip",
        ".tar",
        ".gz",
        ".jpg",
        ".jpeg",
        ".png",
        ".pdf",
      ].includes(extension)
    )
      fail(`${relative}: large/binary dataset artifact is forbidden in Git`);
    if ((await lstat(file)).size > 1_000_000)
      fail(`${relative}: dataset fixture exceeds 1 MB`);
  }
  const governance = await json("contracts/governance/governance.schema.json");
  for (const required of [
    "workClaim",
    "exclusiveResourceLease",
    "providerRun",
    "agentRunEnvelope",
    "agentRunReport",
    "contextCapsule",
    "contextManifest",
    "integrationManifest",
    "agentAssignment",
    "workerReport",
    "reviewFinding",
    "coordinationRequest",
  ]) {
    if (!governance?.$defs?.[required])
      fail(`governance.schema.json: missing ${required}`);
  }
  if (governance?.$defs?.sprintPlan)
    fail("governance.schema.json: obsolete sprintPlan remains");
  if (governance) {
    ajv.addSchema(governance);
    const assignmentValidator = ajv.getSchema(
      `${governance.$id}#/$defs/agentAssignment`,
    );
    const assignmentContext = await resolveContext({
      request: "Complete customer account and privacy journeys",
      paths: [
        "apps/customer-portal/src/platform/api/customer-account/profile-gateway.ts",
      ],
      work: "VFBIZ-0070",
    });
    if (
      !assignmentContext.assignment ||
      !assignmentValidator?.(assignmentContext.assignment)
    )
      fail(
        `generated assignment schema: ${ajv.errorsText(assignmentValidator?.errors)}`,
      );
    const coordinationValidator = ajv.getSchema(
      `${governance.$id}#/$defs/coordinationRequest`,
    );
    const now = new Date().toISOString();
    const coordinationFixture = {
      schemaVersion: 2,
      coordinationId: "coord-contract-test",
      workItemKey: "VFBIZ-0068",
      requestingTeam: "customer-web-experience",
      owningTeam: "api-foundation",
      sharedOutcome: "Keep the customer contract aligned",
      interfaceOrDependency: "Customer profile API",
      factsAlreadyKnown: ["The portal consumes public-v1."],
      decisionOrArtifactNeeded: "Reviewed additive response",
      blocking: false,
      requiredBy: "2026-07-25",
      defaultIfNotBlocking: "Keep the current response.",
      state: "open",
      responses: [],
      createdAt: now,
      updatedAt: now,
    };
    if (!coordinationValidator?.(coordinationFixture))
      fail(
        `coordination request schema: ${ajv.errorsText(coordinationValidator?.errors)}`,
      );
  }
}

function validateOrganizationTopology(organization) {
  const workspaceIds = new Set(organization.workspaces.map(({ id }) => id));
  const departmentIds = new Set();
  const teamIds = new Set();
  const authorities = new Set(organization.humanAuthorities);
  for (const department of organization.departments) {
    if (departmentIds.has(department.id))
      fail(`duplicate department id: ${department.id}`);
    departmentIds.add(department.id);
    if (!authorities.has(department.leadHumanRole))
      fail(`${department.id}: leadHumanRole is not a human authority`);
    for (const workspace of department.workspaces)
      if (!workspaceIds.has(workspace))
        fail(`${department.id}: unknown workspace ${workspace}`);
  }
  for (const team of organization.teams) {
    if (teamIds.has(team.id)) fail(`duplicate team id: ${team.id}`);
    teamIds.add(team.id);
    if (!departmentIds.has(team.departmentId))
      fail(`${team.id}: unknown department ${team.departmentId}`);
    if (!authorities.has(team.leadHumanRole))
      fail(`${team.id}: leadHumanRole is not a human authority`);
    for (const workspace of team.workspaces)
      if (!workspaceIds.has(workspace))
        fail(`${team.id}: unknown workspace ${workspace}`);
  }
  for (const [signal, roles] of Object.entries(organization.authorityRouting))
    for (const role of roles)
      if (!authorities.has(role))
        fail(`${signal}: authority routing uses unknown role ${role}`);
}

const organization = await json(".agents/organization.json");
const scenarios = await json("tests/governance/scenarios.json");
if (organization) {
  validateOrganizationTopology(organization);
  await validateInstructions(organization);
  await validateRolesAndAdapters(organization);
  await validateContextHardening();
  await validateCoordinationLifecycle();
  await validateSkills(organization);
  await validateScenarios(scenarios);
  await validateSchemas(organization);
}

if (failures.length) {
  process.stderr.write(
    `Governance checks failed (${failures.length}):\n${failures.map((value) => `- ${value}`).join("\n")}\n`,
  );
  process.exit(1);
}
process.stdout.write(
  `Governance checks passed: instruction budgets, roles, provider adapters, skills, work schemas and ${scenarios?.scenarios?.length ?? 0} provider-neutral context scenarios.\n`,
);
