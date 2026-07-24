import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const readJson = async (name) =>
  JSON.parse(await readFile(resolve(root, "tokens", name), "utf8"));
const primitive = await readJson("primitive.json");
const semantic = await readJson("semantic.json");
const customer = await readJson("customer.json");
const workforce = await readJson("workforce.json");

function resolveReference(value) {
  if (typeof value !== "string")
    throw new Error("Token values must be strings.");
  const match = value.match(/^\{([^.]+)\.([^}]+)\}$/u);
  if (match === null) return value;
  const [, group, key] = match;
  const resolved = primitive[group]?.[key];
  if (typeof resolved !== "string") throw new Error(`Unknown token ${value}.`);
  return resolved;
}

function css(selector, values) {
  const lines = Object.entries(values)
    .filter(([name]) => name !== "$dark")
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, value]) => {
      const property = name.replace(
        /[A-Z]/gu,
        (letter) => `-${letter.toLowerCase()}`,
      );
      return `  --vfbiz-${property}: ${resolveReference(value)};`;
    });
  return `${selector} {\n${lines.join("\n")}\n}\n`;
}

function cssWithSystemDark(selector, values) {
  const base = css(selector, values);
  if (values.$dark === undefined) return base;
  const dark = css(selector, values.$dark)
    .split("\n")
    .map((line) => (line.length > 0 ? `  ${line}` : line))
    .join("\n");
  return `${base}@media (prefers-color-scheme: dark) {\n${dark}}\n`;
}

const outputs = new Map([
  ["base.css", cssWithSystemDark(":root", semantic)],
  [
    "customer.css",
    cssWithSystemDark(':root, [data-vfbiz-experience="customer"]', customer),
  ],
  [
    "workforce.css",
    cssWithSystemDark(':root, [data-vfbiz-experience="workforce"]', workforce),
  ],
  [
    "tokens.json",
    `${JSON.stringify({ primitive, semantic, customer, workforce }, null, 2)}\n`,
  ],
]);
const mode = process.argv.includes("--check") ? "check" : "write";
let drift = false;
for (const [name, content] of outputs) {
  const target = resolve(root, "generated", name);
  if (mode === "write") {
    await writeFile(target, content, "utf8");
    continue;
  }
  const current = await readFile(target, "utf8").catch(() => "");
  if (current !== content) {
    process.stderr.write(`${name} is not generated from canonical tokens.\n`);
    drift = true;
  }
}
if (drift) process.exitCode = 1;
