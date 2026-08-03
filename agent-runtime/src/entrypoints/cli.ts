#!/usr/bin/env node
import { execFile } from "node:child_process";
import { access, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { cancelRun } from "../application/cancel-run.js";
import {
  buildResumeBrief,
  type ResumeContextRequest,
  type ResumeContextSnapshot,
} from "../application/build-resume-brief.js";
import { assertProgramScope, writeScopeSnapshot } from "../application/check-program-scope.js";
import { decideApproval } from "../application/decide-approval.js";
import { enqueueRun } from "../application/enqueue-run.js";
import { executeRun } from "../application/execute-run.js";
import { resumeRun } from "../application/resume-run.js";
import { RuntimeError } from "../domain/errors.js";
import { createRuntime } from "../index.js";
import { StateCipher } from "../adapters/persistence/sqlite/state-cipher.js";
import {
  assertRuntimeProviderReady,
  loadRuntimeProviderConfiguration,
} from "../config/provider.js";
import { processOne, watch } from "./worker.js";

const execute = promisify(execFile);

function option(args: string[], name: string): string | undefined {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
}

function requiredOption(args: string[], name: string): string {
  const value = option(args, name);
  if (!value) throw new RuntimeError("CLI_ARGUMENT_MISSING", `${name} is required`);
  return value;
}

function output(value: unknown): void {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

async function doctor(): Promise<Record<string, unknown>> {
  const { environment, store } = createRuntime();
  try {
    const organization = JSON.parse(
      await readFile(path.join(environment.repositoryRoot, ".agents/organization.json"), "utf8"),
    ) as { controlPlane?: { multiMachineReady?: boolean }; workspaces?: Array<{ id: string }> };
    const codex = await execute("codex", ["--version"]).then(
      ({ stdout }) => stdout.trim(),
      () => "not-installed",
    );
    await access(environment.stateDirectory);
    const stateDirectoryMode = (await stat(environment.stateDirectory)).mode & 0o777;
    const databaseMode = (await stat(environment.databasePath)).mode & 0o777;
    const agentRuntimeRegistered = organization.workspaces?.some(({ id }) => id === "agent-runtime") ?? false;
    const stateKeyReady = (() => {
      try {
        new StateCipher();
        return true;
      } catch {
        return false;
      }
    })();
    const costPolicyReady = [
      process.env.VFBIZ_AGENT_RUNTIME_INPUT_USD_PER_1M,
      process.env.VFBIZ_AGENT_RUNTIME_OUTPUT_USD_PER_1M,
    ].every((value) => value !== undefined && Number.isFinite(Number(value)) && Number(value) >= 0);
    const providerConfiguration = (() => {
      try {
        return { configuration: loadRuntimeProviderConfiguration(), error: null };
      } catch (error) {
        return {
          configuration: null,
          error: error instanceof RuntimeError ? error.code : "PROVIDER_CONFIGURATION_INVALID",
        };
      }
    })();
    const providerCredentials = (() => {
      if (!providerConfiguration.configuration) return { ready: false, error: providerConfiguration.error };
      try {
        assertRuntimeProviderReady(providerConfiguration.configuration);
        return { ready: true, error: null };
      } catch (error) {
        return {
          ready: false,
          error: error instanceof RuntimeError ? error.code : "PROVIDER_CONFIGURATION_INVALID",
        };
      }
    })();
    const liveProviderReady = providerCredentials.ready && stateKeyReady && costPolicyReady;
    const liveConfigurationSafe = !environment.liveProviderEnabled || liveProviderReady;
    return {
      ok:
        organization.controlPlane?.multiMachineReady === false &&
        agentRuntimeRegistered &&
        stateDirectoryMode === 0o700 &&
        databaseMode === 0o600 &&
        liveConfigurationSafe,
      node: process.version,
      database: environment.databasePath,
      stateDirectoryMode: stateDirectoryMode.toString(8),
      databaseMode: databaseMode.toString(8),
      stateKey: stateKeyReady ? "ready" : "missing-or-invalid",
      costPolicy: costPolicyReady ? "ready" : "missing-or-invalid",
      liveProviderReady,
      liveConfigurationSafe,
      liveProvider: environment.liveProviderEnabled ? "enabled" : "disabled",
      providerKind: providerConfiguration.configuration?.kind ?? "invalid",
      providerApiMode: providerConfiguration.configuration?.apiMode ?? "invalid",
      providerBaseUrlConfigured: Boolean(providerConfiguration.configuration?.baseUrl),
      providerConfigurationError: providerCredentials.error,
      codexFeature: environment.codexEnabled ? "enabled" : "disabled",
      codex,
      fixtureSource: environment.fixtureRepository ?? "built-in-sample-repository",
      agentRuntimeRegistered,
      multiMachineReady: organization.controlPlane?.multiMachineReady ?? null,
    };
  } finally {
    store.close();
  }
}

async function loadResumeContext(
  repositoryRoot: string,
  request: ResumeContextRequest,
): Promise<ResumeContextSnapshot> {
  const baseArgs = [
    path.join(repositoryRoot, "tools/context-resolver.mjs"),
    "--path",
    request.targetPath,
    "--work",
    request.workItemKey,
    "--stage",
    "resume",
  ];
  if (request.runId) baseArgs.push("--run", request.runId);
  const executeResolver = (args: string[]) =>
    execute(process.execPath, args, {
      cwd: repositoryRoot,
      maxBuffer: 2_000_000,
    });
  let stdout: string;
  try {
    const result = await executeResolver(
      request.previousContextKey
        ? [
            ...baseArgs,
            "--previous-context",
            request.previousContextKey,
          ]
        : baseArgs,
    );
    stdout = result.stdout;
  } catch (error) {
    const detail =
      error instanceof Error &&
      "stderr" in error &&
      typeof error.stderr === "string"
        ? error.stderr
        : "";
    if (
      !request.previousContextKey ||
      !/Previous context .* is not available in the shared Git cache/.test(
        detail,
      )
    ) {
      throw error;
    }
    const result = await executeResolver(baseArgs);
    stdout = result.stdout;
  }
  try {
    return JSON.parse(stdout) as ResumeContextSnapshot;
  } catch {
    throw new RuntimeError(
      "RESUME_CONTEXT_INVALID",
      "governance resolver returned an invalid resume context",
    );
  }
}

async function runCli(args = process.argv.slice(2)): Promise<void> {
  const [command, subcommand] = args;
  if (!command) throw new RuntimeError("CLI_COMMAND_MISSING", "agent-runtime command is required");

  if (command === "worker") {
    if (args.includes("--watch")) await watch(option(args, "--worker") ?? undefined);
    else output(await processOne(option(args, "--worker") ?? undefined));
    return;
  }
  if (command === "doctor") {
    output(await doctor());
    return;
  }
  if (command === "eval") {
    const { environment, store } = createRuntime();
    store.close();
    await execute("npm", ["run", "test:evals", "--workspace", "@vfbiz/agent-runtime"], {
      cwd: environment.repositoryRoot,
    }).then(({ stdout, stderr }) => {
      process.stdout.write(stdout);
      process.stderr.write(stderr);
    });
    return;
  }
  if (command === "changed-paths-check" || command === "scope-snapshot") {
    const { environment, store } = createRuntime();
    try {
      if (command === "scope-snapshot") {
        const destination = option(args, "--output") ?? path.join(environment.stateDirectory, "scope-baseline.json");
        output(await writeScopeSnapshot(environment.repositoryRoot, destination));
      } else {
        const baseRevision = option(args, "--base");
        const baselineFile = option(args, "--baseline");
        await assertProgramScope(environment.repositoryRoot, {
          ...(baseRevision ? { baseRevision } : {}),
          ...(baselineFile ? { baselineFile } : {}),
        });
        output({ ok: true, forbiddenProductDiff: false });
      }
    } finally {
      store.close();
    }
    return;
  }
  if (command === "brief") {
    const { environment, store } = createRuntime();
    try {
      const [{ stdout: head }, { stdout: status }] = await Promise.all([
        execute("git", ["rev-parse", "HEAD"], {
          cwd: environment.repositoryRoot,
        }),
        execute("git", ["status", "--porcelain", "--untracked-files=all"], {
          cwd: environment.repositoryRoot,
          maxBuffer: 4_000_000,
        }),
      ]);
      const changedPathCount = status.trim()
        ? status.trimEnd().split(/\r?\n/).length
        : 0;
      const runId = option(args, "--run");
      const workItemKey = option(args, "--work");
      const targetPath = option(args, "--target");
      output(
        await buildResumeBrief(
          {
            headRevision: head.trim(),
            workingTreeDirty: changedPathCount > 0,
            changedPathCount,
            ...(runId ? { runId } : {}),
            ...(workItemKey ? { workItemKey } : {}),
            ...(targetPath ? { targetPath } : {}),
          },
          store,
          (request) =>
            loadResumeContext(environment.repositoryRoot, request),
        ),
      );
    } finally {
      store.close();
    }
    return;
  }

  const { store, governance, agentExecutor } = createRuntime();
  try {
    if (command === "enqueue") {
      const workItemKey = requiredOption(args, "--work");
      const objective = option(args, "--objective");
      const mode = option(args, "--mode") as "discovery" | "bounded" | "controlled" | undefined;
      const idempotencyKey = option(args, "--idempotency-key");
      const governanceClaimId = option(args, "--claim");
      const fencingValue = option(args, "--fencing-token");
      const parsedFencingToken = fencingValue ? Number(fencingValue) : null;
      if (parsedFencingToken !== null && (!Number.isInteger(parsedFencingToken) || parsedFencingToken <= 0)) {
        throw new RuntimeError("CLI_ARGUMENT_INVALID", "--fencing-token must be a positive integer");
      }
      output(await enqueueRun({
        workItemKey,
        targetPath: option(args, "--target") ?? "agent-runtime",
        ...(objective ? { objective } : {}),
        ...(mode ? { mode } : {}),
        ...(idempotencyKey ? { idempotencyKey } : {}),
        ...(governanceClaimId ? { governanceClaimId } : {}),
        ...(parsedFencingToken !== null ? { governanceFencingToken: parsedFencingToken } : {}),
      }, store, governance));
      return;
    }
    if (command === "status") {
      const runId = requiredOption(args, "--run");
      output({
        run: store.getRun(runId),
        events: store.listEvents(runId),
        approvals: store.listApprovals().filter((approval) => approval.runId === runId),
      });
      return;
    }
    if (command === "resume") {
      const run = resumeRun(requiredOption(args, "--run"), store);
      output(run.state === "running"
        ? await executeRun(run.id, store, governance, agentExecutor)
        : run);
      return;
    }
    if (command === "cancel") {
      output(cancelRun(requiredOption(args, "--run"), store));
      return;
    }
    if (command === "approvals") {
      if (subcommand === "list") {
        const status = option(args, "--status") as "pending" | "approved" | "rejected" | undefined;
        output(store.listApprovals(status));
        return;
      }
      if (subcommand === "show") {
        output(store.getApproval(requiredOption(args, "--approval")));
        return;
      }
      if (subcommand === "approve" || subcommand === "reject") {
        output(decideApproval({
          approvalId: requiredOption(args, "--approval"),
          decision: subcommand === "approve" ? "approved" : "rejected",
          decidedBy: requiredOption(args, "--by"),
          reason: requiredOption(args, "--reason"),
        }, store));
        return;
      }
    }
    throw new RuntimeError("CLI_COMMAND_UNKNOWN", `unknown agent-runtime command: ${args.join(" ")}`);
  } finally {
    store.close();
  }
}

runCli().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  const code = error instanceof RuntimeError ? error.code : "UNEXPECTED_ERROR";
  process.stderr.write(`${JSON.stringify({ ok: false, code, message })}\n`);
  process.exitCode = 1;
});
