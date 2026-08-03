import type { ApprovalDecision, RuntimeApproval } from "../domain/approval-decision.js";
import type { ArtifactReference } from "../domain/artifact-reference.js";
import type { RuntimeCheckpoint } from "../domain/runtime-checkpoint.js";
import type { RuntimeEvent, RuntimeEventType } from "../domain/runtime-event.js";
import type { EnqueueRunInput, RuntimeRun, RuntimeState } from "../domain/runtime-run.js";

export interface RuntimeUsage {
  inputTokens: number;
  outputTokens: number;
  estimatedUsd: number | null;
  model: string | null;
}

export interface RuntimeUsageTotals extends RuntimeUsage {
  estimatedUsd: number | null;
  attempts: number;
}

export interface RunStore {
  initialize(): void;
  assertCheckpointEncryptionReady(): void;
  enqueue(input: EnqueueRunInput): RuntimeRun;
  getRun(runId: string): RuntimeRun | null;
  listRuns(workItemKey?: string): RuntimeRun[];
  claimNextRun(workerId: string): RuntimeRun | null;
  heartbeat(runId: string, workerId: string): RuntimeRun;
  resumeWaiting(runId: string, expectedVersion: number, workerId: string): RuntimeRun;
  transition(runId: string, expectedVersion: number, to: RuntimeState, failureCode?: string): RuntimeRun;
  requestCancellation(runId: string): RuntimeRun;
  appendEvent(runId: string, type: RuntimeEventType, idempotencyKey: string, payload: Record<string, unknown>): RuntimeEvent;
  listEvents(runId: string): RuntimeEvent[];
  saveCheckpoint(runId: string, kind: RuntimeCheckpoint["kind"], plaintextState: string): RuntimeCheckpoint;
  getLatestCheckpoint(runId: string): RuntimeCheckpoint | null;
  decryptCheckpoint(checkpoint: RuntimeCheckpoint): string;
  createApproval(input: Omit<RuntimeApproval, "id" | "status" | "decidedBy" | "decisionReason" | "requestedAt" | "decidedAt">): RuntimeApproval;
  getApproval(approvalId: string): RuntimeApproval | null;
  listApprovals(status?: RuntimeApproval["status"]): RuntimeApproval[];
  decideApproval(decision: ApprovalDecision): RuntimeApproval;
  recordArtifact(input: Omit<ArtifactReference, "id" | "createdAt">): ArtifactReference;
  listArtifacts(runId: string): ArtifactReference[];
  recordUsage(runId: string, usage: RuntimeUsage, idempotencyKey: string): void;
  getUsageTotals(runId: string): RuntimeUsageTotals;
  reconcileStale(staleBefore: string): RuntimeRun[];
  close(): void;
}
