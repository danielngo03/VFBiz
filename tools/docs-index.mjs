#!/usr/bin/env node
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFrontmatter } from './lib/frontmatter.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const INDEX = path.join(ROOT, 'docs/INDEX.md');
const MACHINE_INDEX = path.join(ROOT, 'docs/INDEX.json');
const STATUS = new Set(['proposed', 'active', 'superseded', 'archived']);
const DOC_ROOTS = [
  'docs',
  'backend/api/docs',
  'backend/ai/docs',
  'drupal/docs',
  'apps/customer-portal/docs',
  'apps/workforce-portal/docs',
];
const EXCLUDED = new Set(['docs/INDEX.md']);
const TRIGGER_PATTERN =
  /^(?:[a-z0-9]+(?:-[a-z0-9]+)*|VFBIZ-[0-9]{4})$/;

async function walk(directory) {
  const files = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await walk(absolute));
    else if (entry.name.endsWith('.md')) files.push(absolute);
  }
  return files;
}

function isWorkRecord(relative) {
  return relative.startsWith('docs/work/items/')
    || relative === 'docs/work/0000-work-item-template.md'
    || relative === 'docs/work/0000-handoff-template.md';
}

function validateDocument(relative, parsed, organization) {
  const { attributes, body } = parsed;
  const required = ['id', 'title', 'status', 'owner_role', 'scope', 'when_to_read', 'tags', 'revision', 'review_date', 'supersedes'];
  const errors = [];
  for (const key of required) if (!(key in attributes)) errors.push(`${relative}: missing ${key}`);
  if (attributes.status && !STATUS.has(attributes.status)) errors.push(`${relative}: invalid status ${attributes.status}`);
  if (attributes.when_to_read && !Array.isArray(attributes.when_to_read)) errors.push(`${relative}: when_to_read must be an array`);
  if (attributes.tags && !Array.isArray(attributes.tags)) errors.push(`${relative}: tags must be an array`);
  if (attributes.supersedes && !Array.isArray(attributes.supersedes)) errors.push(`${relative}: supersedes must be an array`);
  const roles = new Set([
    ...organization.humanAuthorities,
    ...organization.supportingHumanRoles,
  ]);
  if (attributes.owner_role && !roles.has(attributes.owner_role)) {
    errors.push(`${relative}: owner_role is not canonical: ${attributes.owner_role}`);
  }
  const scopes = new Set([
    ...organization.workspaces.map(({ id }) => id),
    'backend',
    'cross-system',
  ]);
  if (attributes.scope && !scopes.has(attributes.scope)) {
    errors.push(`${relative}: scope is not canonical: ${attributes.scope}`);
  }
  for (const trigger of attributes.when_to_read ?? []) {
    if (typeof trigger !== 'string' || !TRIGGER_PATTERN.test(trigger)) {
      errors.push(`${relative}: invalid when_to_read trigger: ${trigger}`);
    }
  }
  const anchors = attributes.context_anchors ?? {};
  if (
    anchors === null
    || Array.isArray(anchors)
    || typeof anchors !== 'object'
  ) {
    errors.push(`${relative}: context_anchors must be an object`);
  } else {
    const headings = new Set(
      body
        .split(/\r?\n/)
        .filter((line) => /^#{1,3}\s+\S/.test(line))
        .map((line) => line.trim()),
    );
    for (const [trigger, heading] of Object.entries(anchors)) {
      if (!(attributes.when_to_read ?? []).includes(trigger)) {
        errors.push(
          `${relative}: context anchor ${trigger} is not declared in when_to_read`,
        );
      }
      if (typeof heading !== 'string' || !headings.has(heading)) {
        errors.push(
          `${relative}: context anchor ${trigger} targets missing heading ${heading}`,
        );
      }
    }
  }
  if (
    attributes.status === 'active'
    && /^apps\/(?:customer|workforce)-portal\/docs\//.test(relative)
    && (attributes.when_to_read ?? []).length > 0
    && Object.keys(anchors).length === 0
  ) {
    errors.push(`${relative}: active portal documentation requires context_anchors`);
  }
  return errors;
}

export async function buildCatalog() {
  const organization = JSON.parse(
    await readFile(path.join(ROOT, '.agents/organization.json'), 'utf8'),
  );
  const files = [];
  for (const root of DOC_ROOTS) {
    const absolute = path.join(ROOT, root);
    try { files.push(...await walk(absolute)); } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
  }
  const documents = [];
  const errors = [];
  const ids = new Map();
  for (const file of [...new Set(files)].sort()) {
    const relative = path.relative(ROOT, file).split(path.sep).join('/');
    if (EXCLUDED.has(relative) || isWorkRecord(relative)) continue;
    let parsed;
    try { parsed = await readFrontmatter(file); } catch (error) {
      errors.push(error.message);
      continue;
    }
    errors.push(...validateDocument(relative, parsed, organization));
    const id = parsed.attributes.id;
    if (id && ids.has(id)) errors.push(`${relative}: duplicate id ${id} also used by ${ids.get(id)}`);
    else if (id) ids.set(id, relative);
    documents.push({ ...parsed.attributes, path: relative, source_hash: parsed.hash });
  }
  return { version: 1, generated_from: 'YAML frontmatter', documents, errors };
}

function renderIndex(catalog) {
  const rows = catalog.documents
    .sort((a, b) => String(a.scope).localeCompare(String(b.scope)) || String(a.id).localeCompare(String(b.id)))
    .map((doc) => `| ${doc.id} | ${doc.status} | ${doc.scope} | ${doc.owner_role} | [${doc.title}](../${doc.path}) | ${doc.when_to_read.join(', ')} |`);
  return `# Documentation index\n\n> Generated by \`npm run docs:generate\`. Do not edit this file manually.\n\n| ID | Status | Scope | Owner role | Document | When to read |\n| --- | --- | --- | --- | --- | --- |\n${rows.join('\n')}\n`;
}

async function writeCache(catalog) {
  const common = execFileSync('git', ['rev-parse', '--git-common-dir'], { cwd: ROOT, encoding: 'utf8' }).trim();
  const cacheDir = path.resolve(ROOT, common, 'vfbiz-context');
  await mkdir(cacheDir, { recursive: true });
  await writeFile(path.join(cacheDir, 'documentation-catalog.json'), `${JSON.stringify(catalog, null, 2)}\n`);
}

const catalog = await buildCatalog();
if (catalog.errors.length > 0) {
  for (const error of catalog.errors) process.stderr.write(`- ${error}\n`);
  process.exit(1);
}
const rendered = renderIndex(catalog);
if (process.argv.includes('--write')) {
  await writeFile(INDEX, rendered);
  await writeFile(MACHINE_INDEX, `${JSON.stringify(catalog, null, 2)}\n`);
  await writeCache(catalog);
  process.stdout.write(`Generated docs/INDEX.md from ${catalog.documents.length} documents.\n`);
} else if (process.argv.includes('--check')) {
  const current = await readFile(INDEX, 'utf8').catch(() => '');
  const currentMachine = await readFile(MACHINE_INDEX, 'utf8').catch(() => '');
  if (current !== rendered) {
    process.stderr.write('docs/INDEX.md is stale; run npm run docs:generate.\n');
    process.exit(1);
  }
  if (currentMachine !== `${JSON.stringify(catalog, null, 2)}\n`) {
    process.stderr.write('docs/INDEX.json is stale; run npm run docs:generate.\n');
    process.exit(1);
  }
  await writeCache(catalog);
  process.stdout.write(`Documentation index is current (${catalog.documents.length} documents).\n`);
} else {
  process.stdout.write(`${JSON.stringify(catalog, null, 2)}\n`);
}
