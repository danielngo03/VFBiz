import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import yaml from 'js-yaml';

export function parseFrontmatter(content, source = '<memory>') {
  if (!content.startsWith('---\n') && !content.startsWith('---\r\n')) {
    throw new Error(`${source}: missing YAML frontmatter`);
  }
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (!match) throw new Error(`${source}: unterminated YAML frontmatter`);
  const attributes = yaml.load(match[1]) ?? {};
  if (typeof attributes !== 'object' || Array.isArray(attributes)) {
    throw new Error(`${source}: frontmatter must be a mapping`);
  }
  return {
    attributes,
    body: content.slice(match[0].length),
    raw: match[1],
    hash: createHash('sha256').update(content).digest('hex')
  };
}

export async function readFrontmatter(file) {
  return parseFrontmatter(await readFile(file, 'utf8'), file);
}

export function renderFrontmatter(attributes, body) {
  const header = yaml.dump(attributes, {
    lineWidth: 100,
    noRefs: true,
    quotingType: '"',
    forceQuotes: false
  }).trimEnd();
  return `---\n${header}\n---\n\n${body.replace(/^\s+/, '')}`;
}
