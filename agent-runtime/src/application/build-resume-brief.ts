import { RuntimeError } from "../domain/errors.js";
import type {
  ResumeDisposition,
  RuntimeResumeBrief,
} from "../domain/runtime-resume-brief.js";
import { terminalStates, type RuntimeRun } from "../domain/runtime-run.js";
import type { RunStore } from "../ports/run-store.js";

export interface ResumeContextSnapshot {
  contextKey: string;
  workItem: {
    id: string;
    revision: number;
    status: string;
    sections: {
      checkpoint?: { excerpt?: string };
      done_when?: { excerpt?: string };
    };
  };
  resumeDelta: {
    changedSources: string[];
  };
  sourceRevisions: Array<{
    kind: string;
    path: string;
    sourceHash: string;
  }>;
}

export interface ResumeContextRequest {
  workItemKey: string;
  targetPath: string;
  runId?: string;
  previousContextKey?: string;
}

export interface BuildResumeBriefInput {
  runId?: string;
  workItemKey?: string;
  targetPath?: string;
  headRevision: string;
  workingTreeDirty: boolean;
  changedPathCount: number;
  now?: string;
}

export type ResumeContextLoader = (
  request: ResumeContextRequest,
) => Promise<ResumeContextSnapshot>;

function canonicalNextAction(checkpoint: string | null): string | null {
  if (!checkpoint) return null;
  const lines = checkpoint.split(/\r?\n/);
  const start = lines.findIndex((line) => /Exact next action:/i.test(line));
  if (start < 0) return null;
  const first = lines[start]?.replace(/^.*Exact next action:\s*/i, "") ?? "";
  const continuation: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (/^\s*[-*]\s+/.test(line)) break;
    if (line.trim()) continuation.push(line.trim());
  }
  const result = [first.trim(), ...continuation].filter(Boolean).join(" ");
  return result ? result.slice(0, 1_200) : null;
}

function disposition(
  run: RuntimeRun | null,
  stale: boolean,
  pendingApprovals: number,
  now: string,
): ResumeDisposition {
  if (!run) return "no-runtime-run";
  if (stale) return "stale-context";
  if (pendingApprovals > 0 || run.state === "waiting_approval")
    return "human-approval-required";
  if (run.state === "waiting_dependency") return "human-decision-required";
  if (run.state === "queued") return "worker-required";
  if (
    (run.state === "running" || run.state === "reviewing") &&
    (!run.heartbeatAt ||
      Date.parse(run.heartbeatAt) < Date.parse(now) - 5 * 60_000)
  )
    return "reconcile-required";
  return "desktop-review-required";
}

function defaultNextAction(
  value: ResumeDisposition,
  run: RuntimeRun | null,
): string {
  const actions: Record<ResumeDisposition, string> = {
    "no-runtime-run":
      "Continue from the canonical work-item checkpoint; no runtime run is available.",
    "stale-context":
      "Re-resolve repository context and obtain fresh claim authority before any runtime resume.",
    "worker-required":
      "Validate the canonical claim and start one runtime worker for the queued run.",
    "reconcile-required":
      "Run doctor, reconcile the stale worker heartbeat and inspect the latest checkpoint before resume.",
    "human-approval-required":
      "Inspect the pending approval digest and obtain the exact required human authority; agents cannot approve.",
    "human-decision-required":
      "Read the canonical work-item checkpoint and resolve the recorded dependency or decision before resume.",
    "desktop-review-required":
      run && terminalStates.has(run.state)
        ? "Review runtime evidence in Codex Desktop and update the canonical work item; runtime success is not acceptance."
        : "Inspect the active runtime status and canonical checkpoint before deciding whether to wait, cancel or reconcile.",
  };
  return actions[value];
}

export async function buildResumeBrief(
  input: BuildResumeBriefInput,
  store: RunStore,
  loadContext: ResumeContextLoader,
): Promise<RuntimeResumeBrief> {
  const runs = store.listRuns(input.workItemKey);
  const run = input.runId
    ? (runs.find(({ id }) => id === input.runId) ?? null)
    : (runs.find(({ state }) => !terminalStates.has(state)) ?? runs[0] ?? null);
  if (input.runId && !run) {
    throw new RuntimeError(
      "RUN_NOT_FOUND",
      `runtime run not found: ${input.runId}`,
    );
  }
  const workItemKey = run?.workItemKey ?? input.workItemKey;
  const context = workItemKey
    ? await loadContext({
        workItemKey,
        targetPath: input.targetPath ?? run?.workspace ?? "agent-runtime",
        ...(run ? { runId: run.id } : {}),
        ...(run?.contextKey
          ? { previousContextKey: run.contextKey }
          : {}),
      })
    : null;
  const stale = Boolean(
    run &&
      context &&
      (run.contextKey !== context.contextKey ||
        run.baseRevision !== input.headRevision),
  );
  const approvals = run
    ? store.listApprovals().filter(({ runId }) => runId === run.id)
    : [];
  const pendingApprovals = approvals.filter(
    ({ status }) => status === "pending",
  ).length;
  const now = input.now ?? new Date().toISOString();
  const resumeDisposition = disposition(run, stale, pendingApprovals, now);
  const checkpointExcerpt =
    context?.workItem.sections.checkpoint?.excerpt ?? null;
  const latestCheckpoint = run ? store.getLatestCheckpoint(run.id) : null;
  const events = run ? store.listEvents(run.id).slice(-12) : [];
  const artifacts = run ? store.listArtifacts(run.id) : [];
  const usage = run ? store.getUsageTotals(run.id) : null;
  const nextAction =
    canonicalNextAction(checkpointExcerpt) ??
    defaultNextAction(resumeDisposition, run);

  return {
    schemaVersion: 1,
    generatedAt: now,
    repository: {
      headRevision: input.headRevision,
      workingTreeDirty: input.workingTreeDirty,
      changedPathCount: input.changedPathCount,
    },
    workItem: context
      ? {
          id: context.workItem.id,
          revision: context.workItem.revision,
          status: context.workItem.status,
          checkpoint: checkpointExcerpt,
          doneWhen:
            context.workItem.sections.done_when?.excerpt ?? null,
        }
      : null,
    run: run
      ? {
          id: run.id,
          workItemKey: run.workItemKey,
          state: run.state,
          mode: run.mode,
          workspace: run.workspace,
          ownerTeam: run.ownerTeam,
          contextKey: run.contextKey,
          baseRevision: run.baseRevision,
          claimedBy: run.claimedBy,
          heartbeatAt: run.heartbeatAt,
          failureCode: run.failureCode,
          updatedAt: run.updatedAt,
        }
      : null,
    openRuns: store
      .listRuns()
      .filter(({ state }) => !terminalStates.has(state))
      .slice(0, 10)
      .map((candidate) => ({
        id: candidate.id,
        workItemKey: candidate.workItemKey,
        state: candidate.state,
        ownerTeam: candidate.ownerTeam,
        updatedAt: candidate.updatedAt,
      })),
    context: context
      ? {
          currentContextKey: context.contextKey,
          stale,
          changedSources: context.resumeDelta.changedSources.slice(0, 50),
          sourceRevisions: context.sourceRevisions.slice(0, 50),
        }
      : null,
    latestCheckpoint: latestCheckpoint
      ? {
          id: latestCheckpoint.id,
          sequence: latestCheckpoint.sequence,
          kind: latestCheckpoint.kind,
          stateDigest: latestCheckpoint.stateDigest,
          createdAt: latestCheckpoint.createdAt,
        }
      : null,
    approvals: approvals.map((approval) => ({
      id: approval.id,
      toolName: approval.toolName,
      requiredAuthority: approval.requiredAuthority,
      payloadDigest: approval.payloadDigest,
      status: approval.status,
      requestedAt: approval.requestedAt,
    })),
    artifacts: artifacts.map((artifact) => ({
      id: artifact.id,
      kind: artifact.kind,
      path: artifact.path,
      sha256: artifact.sha256,
      mediaType: artifact.mediaType,
      createdAt: artifact.createdAt,
    })),
    usage: usage
      ? {
          inputTokens: usage.inputTokens,
          outputTokens: usage.outputTokens,
          estimatedUsd: usage.estimatedUsd,
          attempts: usage.attempts,
        }
      : null,
    recentEvents: events.map((event) => ({
      sequence: event.sequence,
      type: event.type,
      actor: event.actor,
      contextKey: event.contextKey,
      baseRevision: event.baseRevision,
      payloadDigest: event.payloadDigest,
      createdAt: event.createdAt,
    })),
    disposition: resumeDisposition,
    nextAction,
    safeguards: {
      checkpointDecrypted: false,
      rawEventPayloadIncluded: false,
      claimValidationRequiredBeforeExecution: Boolean(
        run?.governanceClaimId,
      ),
      runtimeSuccessIsAcceptance: false,
    },
  };
}
