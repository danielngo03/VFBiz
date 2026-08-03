export const runtimeEventTypes = [
  "run.enqueued",
  "run.claimed",
  "run.transitioned",
  "run.cancel-requested",
  "run.reconciled",
  "context.resolved",
  "agent.started",
  "agent.completed",
  "agent.failed",
  "checkpoint.saved",
  "approval.requested",
  "approval.decided",
  "artifact.recorded",
  "usage.recorded",
] as const;

export type RuntimeEventType = (typeof runtimeEventTypes)[number];

export interface RuntimeEvent<T = Record<string, unknown>> {
  id: string;
  runId: string;
  sequence: number;
  type: RuntimeEventType;
  idempotencyKey: string;
  actor: string;
  contextKey: string | null;
  baseRevision: string | null;
  payloadDigest: string;
  payload: T;
  createdAt: string;
}
