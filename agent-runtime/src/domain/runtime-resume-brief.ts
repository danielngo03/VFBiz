import type { RuntimeMode, RuntimeState } from "./runtime-run.js";

export type ResumeDisposition =
  | "no-runtime-run"
  | "stale-context"
  | "worker-required"
  | "reconcile-required"
  | "human-approval-required"
  | "human-decision-required"
  | "desktop-review-required";

export interface RuntimeResumeBrief {
  schemaVersion: 1;
  generatedAt: string;
  repository: {
    headRevision: string;
    workingTreeDirty: boolean;
    changedPathCount: number;
  };
  workItem: {
    id: string;
    revision: number;
    status: string;
    checkpoint: string | null;
    doneWhen: string | null;
  } | null;
  run: {
    id: string;
    workItemKey: string;
    state: RuntimeState;
    mode: RuntimeMode;
    workspace: string;
    ownerTeam: string | null;
    contextKey: string | null;
    baseRevision: string | null;
    claimedBy: string | null;
    heartbeatAt: string | null;
    failureCode: string | null;
    updatedAt: string;
  } | null;
  openRuns: Array<{
    id: string;
    workItemKey: string;
    state: RuntimeState;
    ownerTeam: string | null;
    updatedAt: string;
  }>;
  context: {
    currentContextKey: string;
    stale: boolean;
    changedSources: string[];
    sourceRevisions: Array<{
      kind: string;
      path: string;
      sourceHash: string;
    }>;
  } | null;
  latestCheckpoint: {
    id: string;
    sequence: number;
    kind: "workflow" | "agent-state";
    stateDigest: string;
    createdAt: string;
  } | null;
  approvals: Array<{
    id: string;
    toolName: string;
    requiredAuthority: string;
    payloadDigest: string;
    status: "pending" | "approved" | "rejected";
    requestedAt: string;
  }>;
  artifacts: Array<{
    id: string;
    kind: string;
    path: string;
    sha256: string;
    mediaType: string;
    createdAt: string;
  }>;
  usage: {
    inputTokens: number;
    outputTokens: number;
    estimatedUsd: number | null;
    attempts: number;
  } | null;
  recentEvents: Array<{
    sequence: number;
    type: string;
    actor: string;
    contextKey: string | null;
    baseRevision: string | null;
    payloadDigest: string;
    createdAt: string;
  }>;
  disposition: ResumeDisposition;
  nextAction: string;
  safeguards: {
    checkpointDecrypted: false;
    rawEventPayloadIncluded: false;
    claimValidationRequiredBeforeExecution: boolean;
    runtimeSuccessIsAcceptance: false;
  };
}
