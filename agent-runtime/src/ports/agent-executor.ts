import type { AgentResult } from "../agents/agent-result.js";
import type { RuntimeRole } from "../config/model-policy.js";
import type { RuntimeBudget } from "../domain/budget.js";
import type { ResolvedRuntimeContext } from "./governance-gateway.js";

export interface AgentExecutionRequest {
  runId: string;
  objective: string;
  context: ResolvedRuntimeContext;
  budget: RuntimeBudget;
  checkpointState?: string;
  approvalDecisions?: Array<{
    toolName: string;
    interruptionId: string;
    payloadDigest: string;
    decision: "approved" | "rejected";
    reason: string;
  }>;
  signal?: AbortSignal;
}

export interface AgentExecutionOutcome {
  result: AgentResult;
  executedRoles: RuntimeRole[];
  specialistResults: AgentResult[];
  serializedState?: string;
  traceId?: string;
  usage: {
    inputTokens: number;
    outputTokens: number;
    estimatedUsd: number | null;
    model: string | null;
  };
}

export interface AgentExecutor {
  requiresEncryptedCheckpoint?(): boolean;
  execute(request: AgentExecutionRequest): Promise<AgentExecutionOutcome>;
}
