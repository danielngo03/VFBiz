import { mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const appRoot = path.resolve("src/app");
const outputDirectory = path.resolve(".expo/types");
process.env.EXPO_ROUTER_APP_ROOT = appRoot;

await mkdir(outputDirectory, { recursive: true });
const { regenerateDeclarations } = require(
  "@expo/router-server/build/typed-routes",
);
regenerateDeclarations(outputDirectory, {});

// Expo's pinned generator is debounced so editors do not regenerate on every
// file-system event. Wait for that official generator to flush deterministically.
await new Promise((resolve) => setTimeout(resolve, 1_100));
const generated = await stat(path.join(outputDirectory, "router.d.ts"));
if (generated.size === 0) throw new Error("Expo Router generated empty route types.");
