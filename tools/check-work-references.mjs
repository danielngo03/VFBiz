#!/usr/bin/env node
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WORK = path.join(ROOT, "docs/work");
const ITEMS = path.join(WORK, "items");

async function walk(directory) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === "archive") continue;
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) result.push(...(await walk(target)));
    else if (entry.name.endsWith(".md")) result.push(target);
  }
  return result;
}

export async function findMissingWorkReferences({
  workRoot = WORK,
  itemRoot = ITEMS,
} = {}) {
  const names = (await readdir(itemRoot))
    .filter((name) => /^VFBIZ-[0-9]{4}\.md$/.test(name))
    .sort();
  const known = new Set(names.map((name) => name.slice(0, -3)));
  const missing = [];
  for (const file of await walk(workRoot)) {
    const content = await readFile(file, "utf8");
    const references = new Set(content.match(/VFBIZ-[0-9]{4}/g) ?? []);
    for (const reference of references) {
      if (!known.has(reference))
        missing.push(
          `${path.relative(workRoot, file).split(path.sep).join("/")}: ${reference}`,
        );
    }
  }
  return { itemCount: names.length, missing: missing.sort() };
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const result = await findMissingWorkReferences();
  if (result.missing.length > 0) {
    result.missing.forEach((entry) =>
      process.stderr.write(`- unresolved work-item reference ${entry}\n`),
    );
    process.exit(1);
  }
  process.stdout.write(
    `Active work records and plans reference ${result.itemCount} canonical item(s) without dangling IDs.\n`,
  );
}
