#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import Ajv2020 from "ajv/dist/2020.js";

const schemaUrl = new URL(
  "../contracts/authorization/workforce-capability.schema.json",
  import.meta.url,
);
const catalogUrl = new URL(
  "../contracts/authorization/workforce-capabilities.json",
  import.meta.url,
);

const [schema, catalog] = await Promise.all(
  [schemaUrl, catalogUrl].map(async (url) =>
    JSON.parse(await readFile(url, "utf8")),
  ),
);

const ajv = new Ajv2020({ allErrors: true, strict: true });
const valid = ajv.validate(schema, catalog);
if (!valid) {
  console.error(ajv.errors);
  process.exit(1);
}

const keys = catalog.capabilities.map(({ key }) => key);
if (new Set(keys).size !== keys.length) {
  throw new Error("Workforce capability keys must be unique.");
}
if (keys.some((key) => key.includes("*") || key.includes("super-admin"))) {
  throw new Error("Wildcard and super-admin capabilities are forbidden.");
}

console.log(`Validated ${keys.length} workforce capabilities.`);

