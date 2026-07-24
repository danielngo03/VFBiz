import { readdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const themeRoot = join(workspace, "src/main/resources/theme");

async function findTemplates(directory) {
  const templates = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      templates.push(...(await findTemplates(path)));
    } else if (entry.name.endsWith(".ftl")) {
      templates.push(path);
    }
  }
  return templates;
}

const templates = await findTemplates(themeRoot);
const allowedTemplates = new Set([
  join(themeRoot, "vfbiz-foundation/email/html/template.ftl"),
]);
const unexpected = templates.filter(
  (template) => !allowedTemplates.has(template),
);
if (unexpected.length > 0 || templates.length !== allowedTemplates.size) {
  throw new Error(
    `Unexpected FreeMarker overrides:\n${templates.map((path) => `- ${path}`).join("\n")}`,
  );
}

console.log(
  "Template inventory is minimal: one shared email shell and no copied login page.",
);
