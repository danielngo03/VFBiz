#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  access,
  mkdir,
  readFile,
  readdir,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPORTS_DIR = path.join(ROOT, "reports/common");
const IMAGES_DIR = path.join(REPORTS_DIR, "images");
const SOURCE_DIR = path.join(IMAGES_DIR, "source");
const MERMAID_CONFIG = path.join(IMAGES_DIR, "mermaid.config.json");
const SOURCE_MANIFEST = path.join(REPORTS_DIR, "source-manifest.json");
const TOKENS_FILE = path.join(
  ROOT,
  "packages/design-tokens/tokens/primitive.json",
);
const MMDC = path.join(
  ROOT,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "mmdc.cmd" : "mmdc",
);
const EXPECTED_DIAGRAMS = [
  "01-system-landscape",
  "02-experience-channels",
  "03-runtime-containers",
  "04-identity-data-ownership",
  "05-chatbot-runtime",
  "06-knowledge-release",
  "07-ev-planner",
  "08-security-assurance",
  "09-capability-roadmap",
];
const REQUIRED_REPORT_KEYS = [
  "report_id",
  "title",
  "audience",
  "report_scope",
  "owner_role",
  "source_documents",
  "review_date",
];
const TARGET_BANNER =
  "> **Kiến trúc đích, không phản ánh trạng thái triển khai.**";

function fail(messages) {
  for (const message of messages) process.stderr.write(`- ${message}\n`);
  process.exitCode = 1;
}

function parseFrontmatter(content, file) {
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n/);
  if (!match) throw new Error(`${file}: missing YAML frontmatter`);
  const attributes = yaml.load(match[1]);
  if (!attributes || typeof attributes !== "object")
    throw new Error(`${file}: invalid YAML frontmatter`);
  return attributes;
}

async function exists(file) {
  try {
    await access(file);
    return true;
  } catch {
    return false;
  }
}

function collectHexTokens(value, result = new Set()) {
  if (typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value))
    result.add(value.toLowerCase());
  else if (Array.isArray(value))
    value.forEach((item) => collectHexTokens(item, result));
  else if (value && typeof value === "object")
    Object.values(value).forEach((item) => collectHexTokens(item, result));
  return result;
}

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

async function buildSourceManifest() {
  const sources = new Set();
  for (const name of (await readdir(REPORTS_DIR)).filter((entry) =>
    entry.endsWith(".md"),
  )) {
    const file = path.join(REPORTS_DIR, name);
    const attributes = parseFrontmatter(await readFile(file, "utf8"), file);
    for (const reference of attributes.source_documents ?? [])
      sources.add(path.resolve(REPORTS_DIR, reference));
  }
  const generatedFrom = {};
  for (const file of [...sources].sort()) {
    const relative = path.relative(ROOT, file).split(path.sep).join("/");
    generatedFrom[relative] = sha256(await readFile(file));
  }
  return {
    format_version: 1,
    purpose:
      "Detect canonical-source drift in the target-architecture report set.",
    generated_from: generatedFrom,
  };
}

function serializeManifest(manifest) {
  return `${JSON.stringify(manifest, null, 2)}\n`;
}

function renderDiagram(input, output) {
  const result = spawnSync(
    MMDC,
    [
      "--input",
      input,
      "--output",
      output,
      "--configFile",
      MERMAID_CONFIG,
      "--backgroundColor",
      "white",
      "--scale",
      "1.25",
      "--quiet",
    ],
    {
      cwd: ROOT,
      encoding: "utf8",
      env: { ...process.env, NO_COLOR: "1" },
    },
  );
  if (result.status !== 0)
    throw new Error(
      `Mermaid render failed for ${path.relative(ROOT, input)}:\n${
        result.stderr || result.stdout
      }`,
    );
}

async function renderAll(outputDirectory) {
  await mkdir(outputDirectory, { recursive: true });
  for (const name of EXPECTED_DIAGRAMS)
    renderDiagram(
      path.join(SOURCE_DIR, `${name}.mmd`),
      path.join(outputDirectory, `${name}.svg`),
    );
}

async function validateReports() {
  const errors = [];
  const names = (await readdir(REPORTS_DIR))
    .filter((name) => name.endsWith(".md"))
    .sort();
  const expectedReports = [
    "README.md",
    ...Array.from(
      { length: 9 },
      (_, index) => `${String(index + 1).padStart(2, "0")}-`,
    ),
  ];
  if (names.length !== 10)
    errors.push(`expected 10 Markdown reports, found ${names.length}`);
  if (!names.includes(expectedReports[0]))
    errors.push("reports/common/README.md is missing");
  for (const prefix of expectedReports.slice(1))
    if (!names.some((name) => name.startsWith(prefix)))
      errors.push(`report with prefix ${prefix} is missing`);

  const reportIds = new Map();
  for (const name of names) {
    const file = path.join(REPORTS_DIR, name);
    const content = await readFile(file, "utf8");
    let attributes;
    try {
      attributes = parseFrontmatter(content, file);
    } catch (error) {
      errors.push(error.message);
      continue;
    }
    for (const key of REQUIRED_REPORT_KEYS)
      if (
        attributes[key] === undefined ||
        attributes[key] === null ||
        attributes[key] === ""
      )
        errors.push(`${name}: missing ${key}`);
    if (attributes.audience !== "executive-and-technical")
      errors.push(`${name}: audience must be executive-and-technical`);
    if (attributes.report_scope !== "target-architecture")
      errors.push(`${name}: report_scope must be target-architecture`);
    if (!content.includes(TARGET_BANNER))
      errors.push(`${name}: missing target-architecture banner`);
    if (!Array.isArray(attributes.source_documents))
      errors.push(`${name}: source_documents must be a YAML list`);
    else
      for (const reference of attributes.source_documents) {
        const target = path.resolve(REPORTS_DIR, reference);
        if (!(await exists(target)))
          errors.push(`${name}: source document does not exist: ${reference}`);
      }
    const reportId = attributes.report_id;
    if (reportIds.has(reportId))
      errors.push(
        `${name}: duplicate report_id ${reportId} also used by ${reportIds.get(
          reportId,
        )}`,
      );
    else reportIds.set(reportId, name);

    const linkPattern = /!?\[[^\]]*]\(([^)]+)\)/g;
    for (const match of content.matchAll(linkPattern)) {
      const raw = match[1].trim().replace(/^<|>$/g, "");
      if (
        raw.startsWith("#") ||
        /^[a-z][a-z0-9+.-]*:/i.test(raw) ||
        raw.includes(" ")
      )
        continue;
      const reference = raw.split("#")[0];
      if (!reference) continue;
      const target = path.resolve(path.dirname(file), reference);
      if (!(await exists(target)))
        errors.push(`${name}: broken local link ${reference}`);
    }
    if (/!\[[^\]]*]\(https?:\/\//i.test(content))
      errors.push(`${name}: remote image is not allowed`);
    if (/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(content))
      errors.push(`${name}: private key material is forbidden`);
  }
  return errors;
}

async function validateDiagrams(outputDirectory) {
  const errors = [];
  const tokenValues = collectHexTokens(
    JSON.parse(await readFile(TOKENS_FILE, "utf8")),
  );
  const config = await readFile(MERMAID_CONFIG, "utf8");
  const diagramSources = [];

  for (const name of EXPECTED_DIAGRAMS) {
    const sourceFile = path.join(SOURCE_DIR, `${name}.mmd`);
    const outputFile = path.join(outputDirectory, `${name}.svg`);
    if (!(await exists(sourceFile))) {
      errors.push(`missing Mermaid source: ${name}.mmd`);
      continue;
    }
    if (!(await exists(outputFile))) {
      errors.push(`missing SVG output: ${name}.svg`);
      continue;
    }
    const source = await readFile(sourceFile, "utf8");
    diagramSources.push(source);
    if (!/^\s*accTitle:\s+\S/m.test(source))
      errors.push(`${name}.mmd: missing accTitle`);
    if (!/^\s*accDescr:\s+\S/m.test(source))
      errors.push(`${name}.mmd: missing accDescr`);
    if (/https?:\/\//i.test(source))
      errors.push(`${name}.mmd: remote resource is not allowed`);

    const svg = await readFile(outputFile, "utf8");
    if (!/<title\b/i.test(svg))
      errors.push(`${name}.svg: accessible title is missing`);
    if (!/aria-roledescription="flowchart-(?:v2|elk)"/i.test(svg))
      errors.push(`${name}.svg: Mermaid accessibility role is missing`);
    if (
      /<image\b[^>]*(?:href|xlink:href)="https?:/i.test(svg) ||
      /@import\s+url|url\(\s*["']?https?:/i.test(svg) ||
      /<script\b[^>]*\bsrc=/i.test(svg)
    )
      errors.push(`${name}.svg: remote asset/script is not allowed`);
  }

  const usedColors = new Set(
    `${config}\n${diagramSources.join("\n")}`
      .match(/#[0-9a-f]{6}/gi)
      ?.map((value) => value.toLowerCase()) ?? [],
  );
  for (const color of usedColors)
    if (!tokenValues.has(color))
      errors.push(`diagram color ${color} is not defined in primitive tokens`);
  return errors;
}

async function validateSourceManifest() {
  if (!(await exists(SOURCE_MANIFEST)))
    return ["reports/common/source-manifest.json is missing"];
  const expected = serializeManifest(await buildSourceManifest());
  const actual = await readFile(SOURCE_MANIFEST, "utf8");
  return expected === actual
    ? []
    : [
        "canonical report sources changed; review the reports and run npm run reports:build",
      ];
}

const command = process.argv[2] ?? "check";
if (!["build", "check"].includes(command))
  throw new Error("Usage: node tools/reports.mjs <build|check>");

if (command === "build") {
  if (!(await exists(MMDC)))
    throw new Error(
      "Mermaid CLI is unavailable; run npm install before building reports",
    );
  await renderAll(IMAGES_DIR);
  await writeFile(
    SOURCE_MANIFEST,
    serializeManifest(await buildSourceManifest()),
    "utf8",
  );
  const errors = [
    ...(await validateReports()),
    ...(await validateDiagrams(IMAGES_DIR)),
    ...(await validateSourceManifest()),
  ];
  if (errors.length > 0) fail(errors);
  else
    process.stdout.write(
      `Built and validated ${EXPECTED_DIAGRAMS.length} report diagram(s).\n`,
    );
} else {
  const errors = [
    ...(await validateReports()),
    ...(await validateDiagrams(IMAGES_DIR)),
    ...(await validateSourceManifest()),
  ];
  if (errors.length > 0) fail(errors);
  else
    process.stdout.write(
      `Validated 10 report(s), ${EXPECTED_DIAGRAMS.length} diagram(s) and canonical source hashes.\n`,
    );
}
