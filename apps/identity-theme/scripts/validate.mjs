import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const metadata = JSON.parse(
  await readFile(join(workspace, "package.json"), "utf8"),
);
const archive = join(
  workspace,
  "dist",
  `vfbiz-identity-theme-${metadata.version}-kc26.7.0.jar`,
);
const listing = spawnSync("unzip", ["-Z1", archive], { encoding: "utf8" });
if (listing.status !== 0) {
  throw new Error(listing.stderr || `Cannot inspect ${archive}.`);
}

const entries = new Set(listing.stdout.trim().split("\n"));
const required = [
  "META-INF/MANIFEST.MF",
  "META-INF/keycloak-themes.json",
  "theme/vfbiz-foundation/login/theme.properties",
  "theme/vfbiz-foundation/email/theme.properties",
  "theme/vfbiz-customer/login/theme.properties",
  "theme/vfbiz-customer/email/theme.properties",
  "theme/vfbiz-workforce/login/theme.properties",
  "theme/vfbiz-workforce/email/theme.properties",
];
for (const entry of required) {
  if (!entries.has(entry)) {
    throw new Error(`Theme archive is missing ${entry}.`);
  }
}

const manifestRead = spawnSync(
  "unzip",
  ["-p", archive, "META-INF/keycloak-themes.json"],
  { encoding: "utf8" },
);
const manifest = JSON.parse(manifestRead.stdout);
const expectedThemes = [
  "vfbiz-foundation",
  "vfbiz-customer",
  "vfbiz-workforce",
];
if (
  manifest.themes
    .map(({ name }) => name)
    .sort()
    .join(",") !== expectedThemes.sort().join(",")
) {
  throw new Error("Theme manifest does not expose the expected themes.");
}
if (
  manifest.themes.some(
    ({ types }) =>
      types.length !== 2 ||
      !types.includes("login") ||
      !types.includes("email"),
  )
) {
  throw new Error("Only login and email theme types may be exposed.");
}

const prohibited = [
  /https?:\/\//i,
  /@font-face/i,
  /analytics/i,
  /segment\.com/i,
  /googletagmanager/i,
];
for (const entry of entries) {
  if (!/\.(css|js|ftl|properties|json)$/i.test(entry)) continue;
  const content = spawnSync("unzip", ["-p", archive, entry], {
    encoding: "utf8",
  }).stdout;
  for (const pattern of prohibited) {
    if (pattern.test(content)) {
      throw new Error(
        `${entry} contains prohibited remote or tracking content.`,
      );
    }
  }
}

const hashedTokenEntries = [...entries].filter((entry) =>
  /resources\/css\/tokens\/[a-z]+\.[a-f0-9]{12}\.css$/.test(entry),
);
if (hashedTokenEntries.length !== 3) {
  throw new Error(
    "The archive must contain exactly three hashed token assets.",
  );
}

console.log(`Validated ${archive}`);
