import { access, readFile, readdir } from "node:fs/promises";
import { dirname, extname, join, relative, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const sourceRoot = join(root, "src");
const mobileContainer = dirname(root);
const forbiddenImports = [
  "next",
  "server-only",
  "ioredis",
  "pg",
  "@prisma/client",
  "@vfbiz/workforce-api-client",
  "@vfbiz/portal-session-core",
];
const forbiddenText = ["/api/auth/", "backend/ai", "keycloak/admin"];

async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map((entry) => {
      const path = join(directory, entry.name);
      return entry.isDirectory() ? files(path) : [path];
    }),
  );
  return nested.flat();
}

const violations = [];
for (const containerArtifact of ["AGENTS.md", "CLAUDE.md", "README.md", "docs"]) {
  const target = join(mobileContainer, containerArtifact);
  if (await access(target).then(() => true).catch(() => false))
    violations.push(
      `../${containerArtifact} violates the app-owned instruction/docs boundary`,
    );
}
for (const file of await files(sourceRoot)) {
  if (![".ts", ".tsx"].includes(extname(file))) continue;
  const content = await readFile(file, "utf8");
  for (const moduleName of forbiddenImports) {
    const pattern = new RegExp(
      `(?:from\\s+|import\\s*\\()(["'])${moduleName.replaceAll("/", "\\/")}(?:\\/[^"']*)?\\1`,
      "u",
    );
    if (pattern.test(content))
      violations.push(`${relative(root, file)} imports forbidden ${moduleName}`);
  }
  for (const value of forbiddenText)
    if (content.toLowerCase().includes(value))
      violations.push(`${relative(root, file)} contains forbidden boundary ${value}`);
}

if (violations.length) {
  violations.forEach((violation) => process.stderr.write(`- ${violation}\n`));
  process.exit(1);
}
process.stdout.write("Customer Mobile import and endpoint boundaries are clean.\n");
