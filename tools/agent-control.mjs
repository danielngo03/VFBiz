#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import {
  acquireClaim,
  acquireLease,
  handoffClaim,
  heartbeatClaim,
  recordReviewFinding,
  releaseClaim,
  renewLease,
  validateClaim,
  validatePaths,
} from "./lib/agent-control.mjs";

const [entity, action, ...args] = process.argv.slice(2);
const value = (name) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
};
const readJson = async (file) => JSON.parse(await readFile(file, "utf8"));

try {
  let result;
  if (entity === "claim" && action === "acquire")
    result = await acquireClaim(await readJson(value("--input")));
  else if (entity === "claim" && action === "validate")
    result = await validateClaim(value("--claim"), {
      fencingToken: value("--fencing-token"),
    });
  else if (entity === "claim" && action === "heartbeat")
    result = await heartbeatClaim(value("--claim"), value("--fencing-token"));
  else if (entity === "claim" && action === "release")
    result = await releaseClaim(value("--claim"), value("--evidence"));
  else if (entity === "lease" && action === "acquire")
    result = await acquireLease(
      value("--claim"),
      await readJson(value("--input")),
    );
  else if (entity === "lease" && action === "renew")
    result = await renewLease(
      value("--claim"),
      value("--lease"),
      value("--fencing-token"),
    );
  else if (entity === "paths" && action === "validate")
    result = await validatePaths(
      value("--claim"),
      JSON.parse(value("--paths") ?? "[]"),
      { fencingToken: value("--fencing-token") },
    );
  else if (entity === "handoff" && action === "create")
    result = await handoffClaim(
      value("--claim"),
      await readJson(value("--capsule")),
      await readJson(value("--successor")),
    );
  else if (entity === "review" && action === "record-finding")
    result = await recordReviewFinding(
      value("--run"),
      await readJson(value("--input")),
    );
  else throw new Error("unsupported command");
  process.stdout.write(`${JSON.stringify({ ok: true, result })}\n`);
} catch (error) {
  process.stdout.write(
    `${JSON.stringify({ ok: false, code: "AGENT_CONTROL_REJECTED", message: error.message })}\n`,
  );
  process.exitCode = 2;
}
