#!/usr/bin/env node
import {
  closeCoordinationRequest,
  createCoordinationRequest,
  getCoordinationRequest,
  respondCoordinationRequest,
} from "./lib/agent-control.mjs";

function parse(argv) {
  const result = { factsAlreadyKnown: [], evidenceRefs: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    const value = argv[index + 1];
    if (argument === "--blocking") result.blocking = true;
    else if (["--fact", "--evidence"].includes(argument) && value) {
      result[argument === "--fact" ? "factsAlreadyKnown" : "evidenceRefs"].push(
        value,
      );
      index += 1;
    } else if (argument.startsWith("--") && value) {
      const key = argument
        .slice(2)
        .replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
      result[key] = value;
      index += 1;
    } else throw new Error(`Unknown or incomplete argument: ${argument}`);
  }
  return result;
}

function usage() {
  return [
    "Usage:",
    "  node tools/agent-coordinate.mjs create --work-item-key VFBIZ-NNNN --requesting-team TEAM --owning-team TEAM --shared-outcome TEXT --interface-or-dependency TEXT --decision-or-artifact-needed TEXT --required-by DATE [--blocking | --default-if-not-blocking TEXT] [--fact TEXT]",
    "  node tools/agent-coordinate.mjs respond --coordination-id ID --responder-team TEAM --response TEXT [--evidence REF]",
    "  node tools/agent-coordinate.mjs close --coordination-id ID --closed-by TEAM --resolution TEXT",
    "  node tools/agent-coordinate.mjs show --coordination-id ID",
    "",
    "State is local to the shared Git common directory; multi-machine coordination is not supported.",
  ].join("\n");
}

const [command, ...rest] = process.argv.slice(2);
if (!command || command === "--help") {
  process.stdout.write(`${usage()}\n`);
  process.exit(0);
}

try {
  const input = parse(rest);
  let record;
  if (command === "create") {
    input.blocking ??= false;
    record = await createCoordinationRequest(input);
  } else if (command === "respond") {
    record = await respondCoordinationRequest(input);
  } else if (command === "close") {
    record = await closeCoordinationRequest(input);
  } else if (command === "show") {
    record = await getCoordinationRequest(input.coordinationId);
    if (!record) throw new Error("coordination request not found");
  } else {
    throw new Error(`Unsupported command: ${command}`);
  }
  process.stdout.write(`${JSON.stringify(record, null, 2)}\n`);
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
}
