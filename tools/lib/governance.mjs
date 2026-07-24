import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { readFrontmatter } from "./frontmatter.mjs";

const ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const CONTROLLED = new Set([
  "agent-control",
  "ai-dataset",
  "ai-evaluation",
  "ai-assistant",
  "ai-inference",
  "ai-release",
  "ai-retrieval",
  "ai-tool",
  "ai-vision",
  "architecture",
  "authentication",
  "authorization",
  "brand-rights",
  "consent",
  "customer-bff",
  "customer-garage",
  "customer-privacy",
  "customer-profile",
  "customer-data",
  "data-governance",
  "dataset-release",
  "dataset-source",
  "dependency-policy",
  "employee-data",
  "identity-theme",
  "legal",
  "license",
  "local-inference",
  "migration",
  "multimodal-injection",
  "payment",
  "pii",
  "production",
  "public-contract",
  "schema",
  "secret",
  "side-effect",
  "support-handoff",
  "synthetic-dataset",
  "trip-release",
  "vehicle-ownership",
  "workforce-authorization",
  "knowledge-ingestion",
  "knowledge-revision",
]);
const DISCOVERY = new Set([
  "unclear-value",
  "unknown-data",
  "unknown-owner",
  "unknown-provider",
  "unknown-requirement",
]);
const STOP = new Set([
  "data-loss",
  "license-unverified",
  "missing-authorization",
  "no-rollback",
  "pii-leak",
  "secret-leak",
]);
const WORKSPACE_CONTEXT_KEYS = {
  api: [],
  ai: [],
  drupal: ["drupal-boundary"],
  mobile: ["mobile-boundary"],
  "customer-portal": ["customer-portal-boundary"],
  "workforce-portal": ["workforce-portal-boundary"],
  "identity-theme": ["identity-theme-architecture"],
  "design-tokens": [],
  infra: ["infra-boundary"],
  root: [],
};

export async function loadOrganization() {
  return JSON.parse(
    await readFile(path.join(ROOT, ".agents/organization.json"), "utf8"),
  );
}

function repositoryPath(value) {
  if (typeof value !== "string" || value.length === 0 || path.isAbsolute(value))
    throw new Error(`Invalid repository path: ${value}`);
  const absolute = path.resolve(ROOT, value);
  const relative = path.relative(ROOT, absolute);
  if (relative.startsWith("..") || path.isAbsolute(relative))
    throw new Error(`Repository path escapes root: ${value}`);
  return (relative || ".").split(path.sep).join("/");
}

export function resolveWorkspaces(paths, organization) {
  const candidates = organization.workspaces.filter(({ id }) => id !== "root");
  const found = new Set();
  for (const value of paths.length > 0 ? paths : ["."]) {
    const relative = repositoryPath(value);
    const owner = candidates
      .filter(
        ({ path: prefix }) =>
          relative === prefix || relative.startsWith(`${prefix}/`),
      )
      .sort((a, b) => b.path.length - a.path.length)[0];
    found.add(owner?.id ?? "root");
  }
  return [...found].sort();
}

export function resolveTeams(paths, organization) {
  const result = new Set();
  for (const value of paths.length > 0 ? paths : ["."]) {
    const relative = repositoryPath(value);
    const owner = organization.teams
      .flatMap((team) =>
        (team.paths ?? []).map((prefix) => ({
          team,
          prefix: repositoryPath(prefix),
        })),
      )
      .filter(
        ({ prefix }) =>
          relative === prefix || relative.startsWith(`${prefix}/`),
      )
      .sort((left, right) => right.prefix.length - left.prefix.length)[0]?.team;
    if (owner) result.add(owner.id);
  }
  return [...result];
}

function departmentForTeam(teamId, organization) {
  const team = organization.teams.find(({ id }) => id === teamId);
  return team
    ? (organization.departments.find(({ id }) => id === team.departmentId) ??
        null)
    : null;
}

function teamsForSignals(signals) {
  const mapping = [
    [
      "customer-bff",
      ["customer-web-experience", "api-foundation"],
    ],
    ["customer-journey", ["customer-web-experience"]],
    ["design-system", ["customer-web-experience"]],
    ["accessibility", ["customer-web-experience"]],
    ["identity-theme", ["identity-experience"]],
    ["customer-privacy", ["customer-web-experience", "customer-product"]],
    ["workforce-authorization", ["api-foundation", "workforce-experience"]],
    ["customer-profile", ["customer-product"]],
    ["customer-garage", ["customer-product"]],
    ["vehicle-catalog", ["customer-product"]],
    ["vehicle-ownership", ["customer-product"]],
    ["support-handoff", ["customer-engagement"]],
    ["customer-conversation", ["customer-engagement"]],
    ["session-concurrency", ["customer-engagement"]],
    ["ai-assistant", ["ai-assistant-orchestration"]],
    ["ai-inference", ["ai-model-platform", "reliability-engineering"]],
    [
      "ai-vision",
      ["customer-engagement", "ai-assistant-orchestration", "ai-assurance"],
    ],
    [
      "multimodal-injection",
      ["customer-engagement", "ai-assistant-orchestration", "ai-assurance"],
    ],
    ["ai-retrieval", ["ai-knowledge-engineering"]],
    ["ai-release", ["ai-assurance"]],
    ["knowledge-revision", ["ai-knowledge-engineering", "ai-assurance"]],
    [
      "knowledge-ingestion",
      ["ai-knowledge-engineering", "data-governance"],
    ],
    ["local-inference", ["ai-model-platform", "reliability-engineering"]],
    ["dataset-source", ["data-governance"]],
    ["data-governance", ["data-governance"]],
    ["synthetic-dataset", ["ai-knowledge-engineering", "data-governance"]],
    ["dataset-release", ["data-governance", "ai-assurance"]],
  ];
  return mapping.flatMap(([signal, teams]) =>
    signals.has(signal) ? teams : [],
  );
}

function inferSignals(input) {
  const text = [input.request ?? "", ...(input.paths ?? [])]
    .join(" ")
    .toLowerCase();
  const signals = [];
  const rules = [
    [
      "authentication",
      /đăng nhập|oidc|ciam|jwks|authentication|session revoke|mfa/,
    ],
    [
      "customer-bff",
      /customer bff|token vault|opaque session|back-?channel logout|refresh lease/,
    ],
    [
      "authorization",
      /authorization|phân quyền|rbac|abac|cross-subject|cross-customer|entitlement/,
    ],
    [
      "workforce-authorization",
      /workforce authorization|workforce entitlement|dynamic (?:role|authorization)|phân quyền (?:động|nhân sự)|maker-checker|role assignment/,
    ],
    [
      "migration",
      /(?:^|\/)migrations?(?:\/|\b)|database migration|zero-downtime migration/,
    ],
    ["schema", /prisma\/(?:schema|models)|database schema|mô hình dữ liệu/],
    [
      "public-contract",
      /contracts\/openapi|public api contract|openapi\/public|breaking contract/,
    ],
    ["payment", /payment|checkout|thanh toán|đặt cọc/],
    ["pii", /\bpii\b|dữ liệu cá nhân|personal data/],
    [
      "customer-data",
      /customer data|dữ liệu khách hàng|customer profile|garage/,
    ],
    [
      "customer-profile",
      /customer profile|hồ sơ khách hàng|\/me\b|profile update/,
    ],
    [
      "customer-privacy",
      /customer privacy|privacy journey/,
    ],
    [
      "customer-journey",
      /customer journey|account journey|profile journey|security journey|garage journey|luồng khách hàng/,
    ],
    [
      "design-system",
      /design system|design token|visual language|component primitive|giao diện|màu|color|button copy|typography/,
    ],
    [
      "accessibility",
      /accessibility|wcag|screen reader|keyboard navigation|focus state|a11y/,
    ],
    [
      "customer-garage",
      /customer garage|garage entry|garage của (?:tôi|khách hàng)|xe tự khai báo/,
    ],
    [
      "vehicle-catalog",
      /vehicle catalog|catalog xe|model\/variant|mẫu xe|phiên bản xe|vehicle projection/,
    ],
    [
      "vehicle-ownership",
      /vehicle ownership|ownership verification|xác minh (?:xe|sở hữu)|\bvin\b|vehicle association/,
    ],
    ["production", /\bproduction\b|môi trường prod|production operation/],
    [
      "brand-rights",
      /brand rights|asset rights|tài sản thương hiệu|quyền sử dụng (?:ảnh|logo)/,
    ],
    [
      "identity-theme",
      /identity theme|keycloak theme|login theme|email theme|giao diện keycloak/,
    ],
    ["license", /licen[cs]e|bản quyền|provenance/],
    ["secret", /\bsecret\b|api key|private key/],
    ["dependency-policy", /package-lock\.json|composer\.lock/],
    ["ai-dataset", /dataset|ingestion|poisoning|embedding registry/],
    [
      "dataset-source",
      /source register|public dataset(?: candidate)?|dataset (?:download|source)|source candidate|tải (?:xuống )?dataset/,
    ],
    [
      "synthetic-dataset",
      /synthetic dataset|synthetic candidate|sinh (?:bộ )?dataset|generation job/,
    ],
    [
      "dataset-release",
      /dataset release|release dataset|dataset manifest|phát hành dataset/,
    ],
    ["data-governance", /data governance|quản trị dữ liệu|data steward/],
    ["ai-tool", /tool call|tool calling|ai tool|register-ai-tool/],
    [
      "ai-assistant",
      /langgraph|supervisor|conversation graph|graph state|checkpoint migration/,
    ],
    [
      "ai-inference",
      /model mesh|model routing|provider-neutral model|model adapter|provider fallback/,
    ],
    ["ai-retrieval", /\brag\b|retrieval|embedding|citation|groundedness/],
    [
      "ai-evaluation",
      /ai evaluation|model evaluation|validate-ai-release|fine[- ]?tun/,
    ],
    [
      "ai-release",
      /ai release(?: manifest)?|promote model|model release|phát hành ai/,
    ],
    [
      "trip-release",
      /trip (?:planner )?(?:staging |production )?release|validate-trip-release|phát hành trip/,
    ],
    [
      "customer-conversation",
      /customer chatbot|customer chat|conversation session|chat session|hội thoại khách hàng/,
    ],
    [
      "support-handoff",
      /async(?:hronous)? handoff|support handoff|offline handoff|chuyển (?:cho )?nhân viên|mất websocket/,
    ],
    [
      "session-concurrency",
      /session concurrency|concurrent message|message race|optimistic concurrency|\bocc\b|spam (?:phím )?enter|session inbox/,
    ],
    [
      "ai-vision",
      /multimodal|vision (?:model|upload|extraction)|ocr|upload ảnh|hình ảnh taplo/,
    ],
    [
      "multimodal-injection",
      /ocr (?:prompt )?injection|multimodal injection|injection qua (?:ảnh|hình ảnh)|độc chất trong ảnh/,
    ],
    [
      "knowledge-revision",
      /knowledge revision|rag sync|stale vector|knowledge atomic activation|revision barrier|drupal webhook/,
    ],
    [
      "knowledge-ingestion",
      /knowledge-source ingestion|knowledge source ingestion|approved knowledge source|runtime knowledge ingestion/,
    ],
    [
      "local-inference",
      /local inference|local model|vllm|tensorrt|pagedattention|kv[- ]?cache/,
    ],
    [
      "license-unverified",
      /(?:dataset|source).*(?:chưa có quyền|rights? (?:missing|unverified)|license unverified)/,
    ],
  ];
  for (const [signal, pattern] of rules)
    if (pattern.test(text)) signals.push(signal);
  const portalSecurityPath =
    /apps\/(?:customer|workforce)-portal\/src\/(?:app\/(?:api\/auth|bff)|(?:lib\/server|platform)\/(?:auth|session)|proxy(?:\.ts)?)/;
  if (portalSecurityPath.test(text)) {
    signals.push("authentication");
    if (/apps\/customer-portal/.test(text)) signals.push("customer-bff");
  }
  if (
    /apps\/customer-portal\/src\/(?:features\/privacy|app\/.*(?:privacy|data-requests))/.test(
      text,
    )
  ) {
    signals.push("customer-privacy");
  }
  if (
    input.presentationOnly === true &&
    input.reversible !== false &&
    !portalSecurityPath.test(text)
  ) {
    for (let index = signals.length - 1; index >= 0; index -= 1) {
      if (
        [
          "authentication",
          "authorization",
          "customer-bff",
          "customer-data",
          "customer-profile",
          "customer-garage",
          "customer-privacy",
          "pii",
        ].includes(signals[index])
      ) {
        signals.splice(index, 1);
      }
    }
  }
  if (
    /backend\/ai\/app\/modules\/knowledge/.test(text) &&
    !signals.some((value) => value.startsWith("ai-"))
  )
    signals.push("ai-retrieval");
  if (
    /backend\/ai\/app\/modules\/(?:evaluation|governance)/.test(text) &&
    !signals.some((value) => value.startsWith("ai-"))
  )
    signals.push("ai-evaluation");
  if (
    /backend\/ai\/app\/modules\/tooling/.test(text) &&
    !signals.some((value) => value.startsWith("ai-"))
  )
    signals.push("ai-tool");
  if (/drupal/.test(text) && /chatbot widget|ai widget/.test(text)) {
    for (let index = signals.length - 1; index >= 0; index -= 1)
      if (signals[index].startsWith("ai-")) signals.splice(index, 1);
    signals.push("ai-client");
  }
  if (
    signals.some((value) =>
      ["dataset-source", "synthetic-dataset", "dataset-release"].includes(
        value,
      ),
    )
  ) {
    for (let index = signals.length - 1; index >= 0; index -= 1)
      if (signals[index] === "ai-dataset") signals.splice(index, 1);
  }
  return [...new Set(signals)];
}

function authorities(signals, mode, organization) {
  const result = new Set();
  for (const signal of signals)
    for (const role of organization.authorityRouting?.[signal] ?? [])
      result.add(role);
  if (mode === "discovery")
    for (const role of organization.authorityRouting?.discovery ?? [])
      result.add(role);
  return [...result].sort();
}

function resources(paths, signals) {
  const result = new Set();
  for (const value of paths) {
    const relative = repositoryPath(value);
    if (/(?:^|\/)(?:package-lock\.json|composer\.lock)$/.test(relative))
      result.add("dependency-lockfile");
    if (
      /^contracts\/(?:openapi|asyncapi)\//.test(relative) ||
      /openapi|asyncapi/.test(relative)
    )
      result.add("public-contract");
    if (
      /migrations?\//.test(relative) ||
      /^backend\/api\/prisma\/(?:schema\.prisma|models\/)/.test(relative)
    )
      result.add("database-migration");
    if (/^drupal\/(?:config|recipes)\//.test(relative))
      result.add("drupal-config");
    if (/^backend\/ai\/dataset-specs(?:\/|$)/.test(relative))
      result.add("ai-source-registry");
    if (/^\.agents\/organization\.json$/.test(relative))
      result.add("agent-organization-registry");
  }
  if (signals.has("public-contract")) result.add("public-contract");
  if (signals.has("migration") || signals.has("schema"))
    result.add("database-migration");
  if (signals.has("dataset-source")) result.add("ai-source-registry");
  if (signals.has("knowledge-revision"))
    result.add("ai-knowledge-release-registry");
  if (signals.has("ai-dataset") || signals.has("dataset-release"))
    result.add("ai-dataset-registry");
  if (signals.has("agent-control")) result.add("agent-organization-registry");
  return [...result].sort();
}

function reviewProfiles(signals, behaviorChange) {
  const mapping = [
    ["authentication", ["security"]],
    ["identity-theme", ["security", "accessibility", "experience"]],
    ["brand-rights", ["brand-rights"]],
    ["customer-bff", ["security"]],
    ["authorization", ["security", "authorization"]],
    ["workforce-authorization", ["security", "segregation-of-duties"]],
    ["customer-privacy", ["privacy"]],
    ["customer-profile", ["privacy", "data"]],
    ["customer-garage", ["privacy", "data"]],
    ["pii", ["privacy"]],
    ["consent", ["privacy"]],
    ["public-contract", ["contract"]],
    ["migration", ["migration"]],
    ["schema", ["migration", "data"]],
    ["design-system", ["experience"]],
    ["customer-journey", ["experience"]],
    ["accessibility", ["accessibility"]],
    ["ai-assistant", ["ai-safety"]],
    ["ai-tool", ["ai-safety", "authorization"]],
    ["ai-vision", ["ai-safety", "privacy"]],
    ["dataset-source", ["data", "legal"]],
    ["synthetic-dataset", ["data"]],
    ["dataset-release", ["data", "release"]],
    ["production", ["release", "resilience"]],
  ];
  const result = new Set();
  for (const [signal, profiles] of mapping) {
    if (!signals.has(signal)) continue;
    for (const profile of profiles) result.add(profile);
  }
  if (behaviorChange && signals.has("customer-journey")) result.add("experience");
  return [...result].sort();
}

function roles(mode, stage, behaviorChange, signals) {
  if (stage === "review" && signals.has("synthetic-dataset"))
    return ["dataset-quality-reviewer", "risk-reviewer"];
  if (signals.has("dataset-source"))
    return mode === "controlled"
      ? ["orchestrator", "dataset-source-researcher", "risk-reviewer"]
      : ["dataset-source-researcher"];
  if (signals.has("synthetic-dataset"))
    return ["orchestrator", "synthetic-dataset-builder", "risk-reviewer"];
  if (signals.has("dataset-release"))
    return ["orchestrator", "dataset-quality-reviewer", "risk-reviewer"];
  if (stage === "review")
    return mode === "controlled"
      ? ["reviewer-verifier", "risk-reviewer"]
      : ["reviewer-verifier"];
  if (stage === "integration") return ["integrator", "reviewer-verifier"];
  if (mode === "discovery") return ["explorer"];
  if (mode === "parallel") return ["orchestrator", "implementer", "integrator"];
  if (mode === "controlled")
    return [
      "orchestrator",
      "implementer",
      "reviewer-verifier",
      "risk-reviewer",
    ];
  if (mode === "bounded" && behaviorChange)
    return ["implementer", "reviewer-verifier"];
  return ["implementer"];
}

function skills(mode, stage, signals, workspaces) {
  if (mode === "fast") return [];
  if (stage === "resume" || stage === "handoff") return ["handoff-context"];
  if (stage === "review") {
    if (
      signals.has("ai-evaluation") ||
      signals.has("ai-release") ||
      signals.has("dataset-release")
    )
      return ["validate-ai-release", "review-change"];
    if (signals.has("trip-release"))
      return ["validate-trip-release", "review-change"];
    return ["review-change"];
  }
  if (mode === "discovery") return ["triage-change", "plan-change"];
  if (workspaces.includes("ai") && signals.has("synthetic-dataset"))
    return ["generate-synthetic-dataset", "review-change"];
  if (signals.has("dataset-source"))
    return ["onboard-dataset", "review-change"];
  if (signals.has("knowledge-ingestion"))
    return ["deliver-change", "onboard-dataset"];
  if (signals.has("dataset-release"))
    return ["validate-ai-release", "review-change"];
  if (workspaces.includes("ai") && signals.has("ai-dataset"))
    return ["onboard-dataset", "review-change"];
  if (workspaces.includes("ai") && signals.has("ai-tool"))
    return ["register-ai-tool", "review-change"];
  if (
    workspaces.includes("api") &&
    ["schema", "migration", "public-contract"].some((value) =>
      signals.has(value),
    )
  ) {
    return ["evolve-backend-capability", "review-change"];
  }
  if (mode === "parallel") return ["plan-change", "deliver-change"];
  if (mode === "controlled") return ["deliver-change", "review-change"];
  return ["deliver-change"];
}

async function workItem(id) {
  if (!id) return null;
  if (!/^VFBIZ-[0-9]{4}$/.test(id)) throw new Error(`Invalid work ID: ${id}`);
  const file = path.join(ROOT, "docs/work/items", `${id}.md`);
  const parsed = await readFrontmatter(file);
  const lineOffset = parsed.raw.split(/\r?\n/).length + 3;
  const sections = {};
  for (const heading of [
    "# Outcome",
    "## Constraints",
    "## Done when",
    "## Checkpoint",
    "## Evidence",
  ]) {
    const selection = markdownSection(parsed.body, heading, lineOffset);
    sections[
      heading
        .replace(/^#+\s*/, "")
        .toLowerCase()
        .replaceAll(" ", "_")
    ] = selection;
  }
  return {
    id,
    path: path.relative(ROOT, file).split(path.sep).join("/"),
    sections,
    ...parsed,
  };
}

function markdownSection(body, heading, lineOffset = 0) {
  const lines = body.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === heading);
  if (start < 0)
    return { heading, startLine: null, endLine: null, excerpt: "" };
  const level = heading.match(/^#+/)?.[0].length ?? 1;
  const next = lines.findIndex(
    (line, index) =>
      index > start &&
      /^(#+)\s/.test(line) &&
      (level === 1 || (line.match(/^(#+)/)?.[1].length ?? 99) <= level),
  );
  const end = next < 0 ? lines.length : next;
  return {
    heading,
    startLine: start + 1 + lineOffset,
    endLine: end + lineOffset,
    excerpt: lines
      .slice(start + 1, end)
      .join("\n")
      .trim(),
  };
}

function markdownListItems(excerpt) {
  const items = [];
  let current = null;
  for (const line of excerpt.split(/\r?\n/)) {
    const bullet = line.match(/^\s*[-*]\s+(.+)/);
    if (bullet) {
      if (current) items.push(current.trim());
      current = bullet[1];
    } else if (current && line.trim()) current += ` ${line.trim()}`;
  }
  if (current) items.push(current.trim());
  return items;
}

export async function routeChange(input) {
  const organization = await loadOrganization();
  const work = await workItem(input.work);
  const paths = input.paths?.length
    ? input.paths
    : (work?.attributes.allowed_paths ?? []);
  const workspaces = resolveWorkspaces(paths, organization);
  const signalSet = new Set([
    ...(work?.attributes.controlled_signals ?? []),
    ...(input.signals ?? []),
    ...inferSignals({ ...input, paths }),
  ]);
  const uncertainty =
    input.uncertainty ??
    ([...signalSet].some((value) => DISCOVERY.has(value)) ? "high" : "low");
  const hasControl = [...signalSet].some((value) => CONTROLLED.has(value));
  let mode = input.mode ?? work?.attributes.mode;
  if (!mode) {
    if (uncertainty === "high") mode = "discovery";
    else if (hasControl) mode = "controlled";
    else if (workspaces.length > 1 || signalSet.has("coordination"))
      mode = "parallel";
    else if (input.presentationOnly && input.reversible !== false)
      mode = "fast";
    else mode = "bounded";
  }
  if (!organization.deliveryModes[mode])
    throw new Error(`Unsupported delivery mode: ${mode}`);
  const mustStop =
    input.missingAuthority || [...signalSet].some((value) => STOP.has(value));
  const scope =
    signalSet.has("public-contract") || signalSet.has("architecture")
      ? "cross-system"
      : workspaces.length > 1
        ? "cross-workspace"
        : "local";
  const classification = {
    risk: hasControl
      ? mustStop
        ? "critical"
        : "high"
      : mode === "parallel" || input.behaviorChange
        ? "medium"
        : "low",
    complexity:
      mode === "parallel" || input.multiStory
        ? "high"
        : mode === "fast"
          ? "low"
          : "medium",
    uncertainty,
    scope,
    mode,
    artifactLevel:
      mode === "fast"
        ? 0
        : mode === "bounded"
          ? input.multiStory
            ? 2
            : 1
          : mode === "discovery"
            ? 2
            : 3,
    autonomyLevel: mustStop
      ? "E"
      : mode === "controlled" || mode === "discovery"
        ? "D"
        : mode === "parallel"
          ? "C"
          : input.safeDefault
            ? "B"
            : "A",
  };
  const stage = input.stage ?? "delivery";
  const executableWorkStatuses = new Set(["ready", "active", "review"]);
  const requiresWorkItem = ["controlled", "parallel"].includes(mode);
  const workItemReady =
    Boolean(work) && executableWorkStatuses.has(work.attributes.status);
  const needsDecision = requiresWorkItem && !workItemReady;
  const signalTeams = teamsForSignals(signalSet);
  const inferredTeams = [
    ...new Set([...resolveTeams(paths, organization), ...signalTeams]),
  ];
  const ownerTeam = work?.attributes.owner_team ?? inferredTeams[0] ?? null;
  const ownerDepartment = ownerTeam
    ? departmentForTeam(ownerTeam, organization)
    : null;
  const accountableRole =
    work?.attributes.accountable_role ??
    ownerDepartment?.leadHumanRole ??
    (mode === "discovery" ? "product-owner" : "engineering-lead");
  return {
    request: input.request ?? "",
    workItem: work
      ? {
          id: work.id,
          path: work.path,
          revision: work.attributes.revision,
          status: work.attributes.status,
          priority: work.attributes.priority,
          dependsOn: work.attributes.depends_on,
          sections: work.sections,
          sourceHash: work.hash,
        }
      : null,
    paths,
    workspaces,
    signals: [...signalSet].sort(),
    classification,
    ownership: {
      ownerTeam,
      ownerDepartment: ownerDepartment?.id ?? null,
      accountableRole,
      coordinationTeams: inferredTeams.filter((team) => team !== ownerTeam),
    },
    dependencies: work?.attributes.depends_on ?? [],
    declaredExclusiveResources:
      work?.attributes.exclusive_resources ?? [],
    budgets: organization.deliveryModes[mode],
    executionState: needsDecision
      ? "needs-decision"
      : mustStop
        ? "blocked"
        : "ready",
    writerAuthorized: !needsDecision && !mustStop,
    recommendedRoles: roles(mode, stage, input.behaviorChange, signalSet),
    requiredReviewers:
      signalSet.has("synthetic-dataset") || signalSet.has("dataset-release")
        ? ["dataset-quality-reviewer", "risk-reviewer"]
        : signalSet.has("dataset-source")
          ? ["risk-reviewer"]
        : mode === "controlled"
          ? ["reviewer-verifier", "risk-reviewer"]
          : input.behaviorChange && mode === "bounded"
            ? ["reviewer-verifier"]
            : [],
    reviewProfiles: reviewProfiles(signalSet, input.behaviorChange),
    requiredAuthorities: authorities(signalSet, mode, organization),
    requiredSkills: skills(mode, stage, signalSet, workspaces),
    stopConditions: [
      ...(needsDecision
        ? [
            "A valid ready, active or review work item is required before a controlled or parallel writer can be assigned.",
          ]
        : []),
      ...(mustStop
        ? [
            "Named human authority or verified evidence is required before the affected lane continues.",
          ]
        : []),
    ],
  };
}

async function activeDocuments() {
  const catalog = JSON.parse(
    await readFile(path.join(ROOT, "docs/INDEX.json"), "utf8"),
  );
  return catalog.documents.filter(
    (document) =>
      document.status === "active" && !document.path.includes("/archive/"),
  );
}

async function headingSelection(document, keys) {
  const parsed = await readFrontmatter(path.join(ROOT, document.path));
  const lines = parsed.body.split(/\r?\n/);
  const headings = lines
    .map((line, index) => ({ line, index }))
    .filter(({ line }) => /^#{1,3}\s+/.test(line));
  const anchor = [...keys]
    .map((key) => document.context_anchors?.[key])
    .find(Boolean);
  if (anchor) {
    const exact = headings.find(({ line }) => line.trim() === anchor);
    if (!exact) {
      throw new Error(
        `${document.path}: configured context anchor targets missing heading ${anchor}`,
      );
    }
    const level = exact.line.match(/^#+/)?.[0].length ?? 1;
    const next = headings.find(
      ({ index, line }) =>
        index > exact.index && (line.match(/^#+/)?.[0].length ?? 99) <= level,
    );
    const endIndex = next
      ? next.index
      : Math.min(lines.length, exact.index + 60);
    const lineOffset = parsed.raw.split(/\r?\n/).length + 3;
    return {
      heading: exact.line,
      anchorKey: [...keys].find(
        (key) => document.context_anchors?.[key] === anchor,
      ),
      startLine: exact.index + 1 + lineOffset,
      endLine: endIndex + lineOffset,
      excerpt: lines.slice(exact.index, endIndex).join("\n").trim(),
      sourceHash: parsed.hash,
    };
  }
  const keyTokens = new Set(
    [...keys].flatMap((key) => {
      const normalized = String(key).replaceAll("-", " ").toLowerCase();
      const tokens = normalized
        .split(/[^\p{L}\p{N}]+/u)
        .filter((token) => token.length > 2);
      if (tokens.includes("authorization"))
        tokens.push("authority", "security");
      if (tokens.includes("authentication"))
        tokens.push("identity", "security");
      if (tokens.includes("controlled")) tokens.push("security", "authority");
      return tokens;
    }),
  );
  const scored = headings.map((heading) => ({
    ...heading,
    level: heading.line.match(/^#+/)?.[0].length ?? 1,
    score: [...keyTokens].filter((token) =>
      heading.line.toLowerCase().includes(token),
    ).length,
  }));
  const nestedMatches = scored.filter(
    ({ level, score }) => level > 1 && score > 0,
  );
  const nested = scored.filter(({ level }) => level > 1);
  const pool = nestedMatches.length
    ? nestedMatches
    : nested.length
      ? nested
      : scored;
  const best = [...pool].sort(
    (left, right) =>
      right.score - left.score ||
      right.level - left.level ||
      left.index - right.index,
  )[0] ?? { line: "# Document", index: 0 };
  const level = best.line.match(/^#+/)?.[0].length ?? 1;
  const next = headings.find(
    ({ index, line }) =>
      index > best.index && (line.match(/^#+/)?.[0].length ?? 99) <= level,
  );
  const endIndex = next ? next.index : Math.min(lines.length, best.index + 60);
  const lineOffset = parsed.raw.split(/\r?\n/).length + 3;
  return {
    heading: best.line,
    startLine: best.index + 1 + lineOffset,
    endLine: endIndex + lineOffset,
    excerpt: lines.slice(best.index, endIndex).join("\n").trim(),
    sourceHash: parsed.hash,
  };
}

async function instructionPaths(paths, workspaces, organization) {
  const result = ["AGENTS.md"];
  for (const id of workspaces) {
    const workspace = organization.workspaces.find((item) => item.id === id);
    if (!workspace || workspace.id === "root") continue;
    const segments = workspace.path.split("/");
    for (let depth = 1; depth <= segments.length; depth += 1) {
      const candidate = `${segments.slice(0, depth).join("/")}/AGENTS.md`;
      try {
        await readFile(path.join(ROOT, candidate), "utf8");
        result.push(candidate);
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
    }
  }
  for (const value of paths) {
    const relative = repositoryPath(value);
    if (relative === ".") continue;
    let segments = relative.split("/");
    try {
      if ((await stat(path.join(ROOT, relative))).isFile())
        segments = segments.slice(0, -1);
    } catch {
      /* Future paths are treated as directories for instruction discovery. */
    }
    for (let depth = 1; depth <= segments.length; depth += 1) {
      const candidate = `${segments.slice(0, depth).join("/")}/AGENTS.md`;
      try {
        await readFile(path.join(ROOT, candidate), "utf8");
        result.push(candidate);
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
    }
  }
  return [...new Set(result)];
}

async function sourceDescriptor(sourcePath, kind) {
  const content = await readFile(path.join(ROOT, sourcePath), "utf8");
  return {
    kind,
    path: sourcePath,
    sourceHash: createHash("sha256").update(content).digest("hex"),
  };
}

async function skillSourcePath(id) {
  for (const candidate of [
    `.agents/skills/${id}/SKILL.md`,
    `backend/api/.agents/skills/${id}/SKILL.md`,
    `backend/ai/.agents/skills/${id}/SKILL.md`,
  ]) {
    try {
      await stat(path.join(ROOT, candidate));
      return candidate;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
    }
  }
  return null;
}

function contextCacheDirectory() {
  const common = execFileSync("git", ["rev-parse", "--git-common-dir"], {
    cwd: ROOT,
    encoding: "utf8",
  }).trim();
  return path.resolve(ROOT, common, "vfbiz-context");
}

async function previousSourceHashMap(input) {
  const result = new Map(
    Object.entries(input.previousSourceHashes ?? {}).filter(
      ([sourcePath, hash]) =>
        typeof sourcePath === "string" && /^[a-f0-9]{64}$/.test(hash),
    ),
  );
  if (!input.previousContextKey) return result;
  if (!/^[a-f0-9]{64}$/.test(input.previousContextKey)) {
    throw new Error("previous context key must be a SHA-256 value");
  }
  try {
    const previous = JSON.parse(
      await readFile(
        path.join(
          contextCacheDirectory(),
          `${input.previousContextKey}.json`,
        ),
        "utf8",
      ),
    );
    for (const source of previous.sourceRevisions ?? []) {
      if (source?.path && /^[a-f0-9]{64}$/.test(source.sourceHash)) {
        result.set(source.path, source.sourceHash);
      }
    }
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    throw new Error(
      `Previous context ${input.previousContextKey} is not available in the shared Git cache`,
    );
  }
  return result;
}

export async function resolveContext(input) {
  const organization = await loadOrganization();
  const route = await routeChange(input);
  const ownerTeam = organization.teams.find(
    ({ id }) => id === route.ownership.ownerTeam,
  );
  const relevantScopes = new Set([
    ...route.workspaces,
    ...(ownerTeam?.workspaces ?? []),
    "root",
    "cross-system",
  ]);
  if (route.workspaces.some((workspace) => ["api", "ai"].includes(workspace)))
    relevantScopes.add("backend");
  const keys = new Set(
    [
      ...route.signals,
      ...route.workspaces,
      ...route.workspaces.flatMap(
        (workspace) => WORKSPACE_CONTEXT_KEYS[workspace] ?? [],
      ),
      route.ownership.ownerTeam,
      route.ownership.ownerDepartment,
    ].filter(Boolean),
  );
  const candidates = (await activeDocuments())
    .filter((document) => relevantScopes.has(document.scope))
    .map((document) => {
      const when = document.when_to_read ?? [];
      const specializedGroups = [
        [
          "workforce",
          ["workforce-authorization", "workforce-admin", "workforce-portal"],
        ],
      ];
      const mismatchedSpecialization = specializedGroups.some(
        ([, markers]) =>
          markers.some((marker) => when.includes(marker)) &&
          !markers.some((marker) => keys.has(marker)),
      );
      const matched = mismatchedSpecialization
        ? []
        : when.filter((value) => keys.has(value));
      return { document, matched, score: matched.length * 10 };
    })
    .filter(
      ({ matched }) =>
        matched.length > 0 && route.classification.mode !== "fast",
    )
    .sort(
      (a, b) => b.score - a.score || a.document.id.localeCompare(b.document.id),
    )
    .slice(0, route.budgets.maxDocs);
  const documents = await Promise.all(
    candidates.map(async ({ document, matched }) => ({
      id: document.id,
      path: document.path,
      revision: document.revision,
      reason: matched,
      selection: await headingSelection(document, matched),
    })),
  );
  const exclusiveResources = [
    ...new Set([
      ...resources(route.paths, new Set(route.signals)),
      ...(route.declaredExclusiveResources ?? []),
    ]),
  ].sort();
  const instructions = await instructionPaths(
    route.paths,
    route.workspaces,
    organization,
  );
  const roleId =
    route.recommendedRoles.find((role) => role !== "orchestrator") ??
    "implementer";
  const role = organization.roles.find(({ id }) => id === roleId);
  const roleSource = await sourceDescriptor(
    `.agents/roles/${roleId}.md`,
    "role",
  );
  const primaryWorkspace =
    organization.workspaces.find(({ id }) => id === route.workspaces[0]) ??
    organization.workspaces[0];
  const parsedAcceptance = route.workItem?.sections?.done_when?.excerpt
    ? markdownListItems(route.workItem.sections.done_when.excerpt)
    : [];
  const acceptance = parsedAcceptance?.length
    ? parsedAcceptance
    : ["Satisfy the requested outcome and observed workspace checks."];
  const instructionSources = await Promise.all(
    instructions.map((instructionPath) =>
      sourceDescriptor(instructionPath, "instruction"),
    ),
  );
  const skillSources = [];
  for (const id of route.requiredSkills.slice(0, 2)) {
    const skillPath = await skillSourcePath(id);
    if (skillPath) {
      skillSources.push({
        id,
        ...(await sourceDescriptor(skillPath, "skill")),
      });
    }
  }
  const documentSources = documents.map(({ path: documentPath, selection }) => ({
    kind: "document",
    path: documentPath,
    sourceHash: selection.sourceHash,
  }));
  const sourceRevisions = [
    ...instructionSources,
    roleSource,
    ...skillSources,
    ...documentSources,
  ];
  const manifest = {
    generatedFrom: { organizationVersion: organization.version },
    stage: input.stage ?? "delivery",
    ...route,
    instructions: instructionSources.map(({ path: sourcePath, sourceHash }) => ({
      path: sourcePath,
      sourceHash,
    })),
    documents,
    sourceRevisions,
    exclusivePaths: route.paths.filter((value) =>
      /contract|migration|config|lock|dataset|registry/i.test(value),
    ),
    exclusiveResources,
    claimRequired:
      route.classification.mode === "controlled" ||
      route.classification.mode === "parallel" ||
      input.delegated === true,
    maxConcurrentWriters: organization.runtime.maxWriterLanes,
    exitStates: organization.exitStates,
    assignment: route.writerAuthorized
      ? {
          work_id: route.workItem?.id ?? null,
          run_id: input.runId ?? null,
          role: roleId,
          owner_team: route.ownership.ownerTeam,
          accountable_role: route.ownership.accountableRole,
          objective:
            input.request ||
            route.workItem?.sections?.outcome?.excerpt ||
            "Complete the bounded repository change.",
          working_directory: primaryWorkspace.path,
          allowed_paths: route.paths,
          dependencies: route.dependencies,
          exclusive_resources: exclusiveResources,
          required_context: [
            ...instructions,
            ...documents.map(
              ({ path: documentPath, selection }) =>
                `${documentPath}:${selection.startLine}-${selection.endLine}`,
            ),
          ],
          review_profiles: route.reviewProfiles,
          deliverable:
            input.stage === "review"
              ? "A read-only verification report with observed evidence."
              : "A bounded implementation and concise worker report.",
          acceptance,
          tools_allowed: role?.capabilities ?? ["read", "search"],
          may_delegate: false,
          max_turns: role?.maxTurns ?? 20,
          stop_conditions: route.stopConditions.length
            ? route.stopConditions
            : ["Stop on scope, authority, lease or safety violations."],
        }
      : null,
  };
  const contextKey = createHash("sha256")
    .update(JSON.stringify(manifest))
    .digest("hex");
  const previousHashes = await previousSourceHashMap(input);
  const changedSources = sourceRevisions
    .filter(
      ({ path: sourcePath, sourceHash }) =>
        previousHashes.get(sourcePath) !== sourceHash,
    )
    .map(({ path: sourcePath }) => sourcePath);
  const unchangedSources = sourceRevisions
    .filter(
      ({ path: sourcePath, sourceHash }) =>
        previousHashes.get(sourcePath) === sourceHash,
    )
    .map(({ path: sourcePath }) => sourcePath);
  const result = {
    contextKey,
    ...manifest,
    resumeDelta: {
      previousContextKey: input.previousContextKey ?? null,
      changedSources,
      unchangedSources,
    },
  };
  try {
    const cache = contextCacheDirectory();
    await mkdir(cache, { recursive: true });
    await pruneContextCache(cache);
    await writeFile(
      path.join(cache, `${contextKey}.json`),
      `${JSON.stringify(result, null, 2)}\n`,
    );
  } catch {
    /* Context resolution remains usable without a writable Git cache. */
  }
  return result;
}

async function pruneContextCache(cache) {
  const maximumAge = 7 * 24 * 60 * 60 * 1_000;
  const entries = [];
  for (const name of await readdir(cache)) {
    if (!name.endsWith(".json") || name === "documentation-catalog.json")
      continue;
    const file = path.join(cache, name);
    const info = await stat(file);
    if (Date.now() - info.mtimeMs > maximumAge) await rm(file, { force: true });
    else entries.push({ file, mtimeMs: info.mtimeMs });
  }
  for (const entry of entries
    .sort((left, right) => right.mtimeMs - left.mtimeMs)
    .slice(200))
    await rm(entry.file, { force: true });
}

export { ROOT };
