#!/usr/bin/env node
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const schemaPaths = [
  'contracts/json-schema/citation.schema.json',
  'contracts/json-schema/dataset-release-manifest.schema.json',
  'contracts/json-schema/ai-release-manifest.schema.json',
];
const ajv = new Ajv2020({ strict: true, allErrors: true });
addFormats(ajv);

for (const relativePath of schemaPaths) {
  const schema = JSON.parse(await readFile(path.join(root, relativePath), 'utf8'));
  ajv.compile(schema);
}

console.log(`Runtime contract schemas compiled: ${schemaPaths.length}`);
