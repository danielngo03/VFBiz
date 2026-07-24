import { createHash } from "node:crypto";
import {
  cp,
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  utimes,
  writeFile,
} from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repository = resolve(workspace, "../..");
const packageMetadata = JSON.parse(
  await readFile(join(workspace, "package.json"), "utf8"),
);
const keycloakVersion = "26.7.0";
const buildRoot = join(workspace, ".build");
const stage = join(buildRoot, "jar");
const dist = join(workspace, "dist");
const archiveName = `vfbiz-identity-theme-${packageMetadata.version}-kc${keycloakVersion}.jar`;
const archive = join(dist, archiveName);
const fixedDate = new Date(
  Number(process.env.SOURCE_DATE_EPOCH ?? "1735689600") * 1000,
);

function digest(content) {
  return createHash("sha256").update(content).digest("hex").slice(0, 12);
}

async function copyHashedToken(tokenName, themeName) {
  const source = join(
    repository,
    "packages/design-tokens/generated",
    `${tokenName}.css`,
  );
  const content = await readFile(source, "utf8");
  const fileName = `${tokenName}.${digest(content)}.css`;
  const targetDirectory = join(
    stage,
    "theme",
    themeName,
    "login/resources/css/tokens",
  );
  await mkdir(targetDirectory, { recursive: true });
  await writeFile(join(targetDirectory, fileName), content);

  const themeStylesheet = join(
    stage,
    "theme",
    themeName,
    "login/resources/css",
    `vfbiz-${tokenName === "base" ? "foundation" : tokenName}.css`,
  );
  const stylesheet = await readFile(themeStylesheet, "utf8");
  await writeFile(
    themeStylesheet,
    stylesheet.replace(`./tokens/${tokenName}.css`, `./tokens/${fileName}`),
  );
}

async function normalizeTimestamps(path) {
  const metadata = await stat(path);
  if (metadata.isDirectory()) {
    const entries = await readdir(path);
    for (const entry of entries.sort()) {
      await normalizeTimestamps(join(path, entry));
    }
  }
  await utimes(path, fixedDate, fixedDate);
}

async function listFiles(path, prefix = "") {
  const files = [];
  for (const entry of (await readdir(path, { withFileTypes: true })).sort(
    (left, right) => left.name.localeCompare(right.name),
  )) {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      files.push(...(await listFiles(join(path, entry.name), relative)));
    } else {
      files.push(relative);
    }
  }
  return files;
}

await rm(buildRoot, { recursive: true, force: true });
await rm(dist, { recursive: true, force: true });
await mkdir(stage, { recursive: true });
await mkdir(dist, { recursive: true });
await cp(join(workspace, "src/main/resources"), stage, { recursive: true });

await copyHashedToken("base", "vfbiz-foundation");
await copyHashedToken("customer", "vfbiz-customer");
await copyHashedToken("workforce", "vfbiz-workforce");
await normalizeTimestamps(stage);

const files = await listFiles(stage);
const zip = spawnSync("zip", ["-X", "-q", archive, "-@"], {
  cwd: stage,
  input: `${files.join("\n")}\n`,
  encoding: "utf8",
});
if (zip.status !== 0) {
  throw new Error(zip.stderr || "Unable to create the Keycloak theme JAR.");
}

const checksum = createHash("sha256")
  .update(await readFile(archive))
  .digest("hex");
await writeFile(`${archive}.sha256`, `${checksum}  ${archiveName}\n`);

console.log(`Built ${archive}`);
console.log(`SHA-256 ${checksum}`);
