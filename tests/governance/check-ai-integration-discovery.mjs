import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const packageDocument = JSON.parse(
  await readFile(new URL("../../package.json", import.meta.url), "utf8"),
);
const command = packageDocument.scripts?.["verify:ai:integration"];

assert.equal(typeof command, "string", "AI integration command must exist");
assert.match(
  command,
  /pytest\s+tests\/integration(?:\s|$)/,
  "AI release integration must retain the shared integration suite",
);
assert.match(
  command,
  /tests\/evaluation\/test_postgres_evaluation_run_registry\.py/,
  "AI release integration must discover the governed evaluation registry test",
);

process.stdout.write("AI integration discovery is governed.\n");
