import { createHash } from "node:crypto";
import { OpenAIProvider, RunState, Runner, tool, type Tool } from "@openai/agents";
import { z } from "zod";
import { EnvironmentModelPolicy, type ModelPolicy } from "../../config/model-policy.js";
import type { RuntimeRole } from "../../config/model-policy.js";
import {
  assertRuntimeProviderReady,
  loadRuntimeProviderConfiguration,
} from "../../config/provider.js";
import { RuntimeError } from "../../domain/errors.js";
import { createOrchestratorAgent } from "../../agents/orchestrator-agent.js";
import { agentResultSchema, failedSafely, type AgentResult } from "../../agents/agent-result.js";
import type { AgentExecutionOutcome, AgentExecutionRequest, AgentExecutor } from "../../ports/agent-executor.js";
import type { CodingExecutor } from "../../ports/coding-executor.js";

interface ApprovalItem {
  name: string | undefined;
  arguments: string | undefined;
  rawItem: {
    callId?: string | undefined;
    id?: string | undefined;
  };
}

interface ApprovalCapableState<TItem extends ApprovalItem> {
  getInterruptions(): TItem[];
  approve(item: TItem): void;
  reject(item: TItem, options: { message: string }): void;
}

export function applyApprovalDecisions<TItem extends ApprovalItem>(
  state: ApprovalCapableState<TItem>,
  decisions: NonNullable<AgentExecutionRequest["approvalDecisions"]>,
): void {
  for (const interruption of state.getInterruptions()) {
    const interruptionId = approvalInterruptionId(interruption);
    const payloadDigest = createHash("sha256")
      .update(interruption.arguments ?? "{}")
      .digest("hex");
    const decision = decisions.find(
      (candidate) =>
        candidate.toolName === (interruption.name ?? "unknown-tool") &&
        candidate.interruptionId === interruptionId &&
        candidate.payloadDigest === payloadDigest,
    );
    if (!decision) {
      throw new RuntimeError("APPROVAL_DECISION_MISSING", "checkpoint has an undecided tool interruption");
    }
    if (decision.decision === "approved") state.approve(interruption);
    else state.reject(interruption, { message: decision.reason });
  }
}

export function approvalInterruptionId(item: ApprovalItem): string {
  const value = item.rawItem.callId ?? item.rawItem.id;
  if (!value) {
    throw new RuntimeError("APPROVAL_ID_MISSING", "Agents SDK interruption has no stable call identity");
  }
  return value;
}

export function executedRuntimeRoles(items: unknown[]): RuntimeRole[] {
  return ["orchestrator", ...new Set(extractSpecialistResults(items).map(({ role }) => role))];
}

export function extractSpecialistResults(items: unknown[]) {
  const results: AgentResult[] = [];
  for (const item of items) {
    const rawItem = typeof item === "object" && item !== null && "rawItem" in item
      ? (item as { rawItem?: { type?: unknown; name?: unknown; output?: unknown } }).rawItem
      : undefined;
    if (
      rawItem?.type !== "function_call_result" ||
      typeof rawItem.name !== "string" ||
      !rawItem.name.startsWith("ask_")
    ) continue;
    const output = toolResultText(rawItem.output);
    if (output === null) continue;
    const role = rawItem.name.slice(4).replaceAll("_", "-") as RuntimeRole;
    if (!["explorer", "implementer", "reviewer-verifier", "risk-reviewer", "integrator"].includes(role)) continue;
    const decoded = (() => {
      try {
        return JSON.parse(output) as unknown;
      } catch {
        return null;
      }
    })();
    const parsed = agentResultSchema.safeParse(decoded);
    if (parsed.success && parsed.data.role === role) results.push(parsed.data);
  }
  return results;
}

function toolResultText(output: unknown): string | null {
  if (typeof output === "string") return output;
  if (
    typeof output === "object" &&
    output !== null &&
    "type" in output &&
    output.type === "text" &&
    "text" in output &&
    typeof output.text === "string"
  ) return output.text;
  return null;
}

export function buildRunnerTraceConfiguration(
  request: Pick<AgentExecutionRequest, "runId" | "context">,
  traceEnabled: boolean,
) {
  return {
    tracingDisabled: !traceEnabled,
    traceIncludeSensitiveData: false,
    workflowName: "VFBiz enterprise agent runtime",
    groupId: request.context.workItemKey,
    traceMetadata: {
      work_item: request.context.workItemKey,
      run: request.runId,
      role: "orchestrator",
      team: request.context.ownerTeam,
      workspace: request.context.workspace,
      context_key: request.context.contextKey,
      revision: request.context.baseRevision,
    },
  };
}

export class AgentsSdkExecutor implements AgentExecutor {
  public constructor(
    private readonly enabled: boolean,
    private readonly traceEnabled: boolean,
    private readonly models: ModelPolicy = new EnvironmentModelPolicy(),
    private readonly codingExecutor?: CodingExecutor,
    private readonly fixtureRepository?: string,
    private readonly source: NodeJS.ProcessEnv = process.env,
  ) {}

  public requiresEncryptedCheckpoint(): boolean {
    return this.enabled;
  }

  public async execute(request: AgentExecutionRequest): Promise<AgentExecutionOutcome> {
    if (!this.enabled) {
      return {
        result: failedSafely(
          "orchestrator",
          "Live model-provider execution is disabled; deterministic intake completed without model mutation.",
        ),
        executedRoles: ["orchestrator"],
        specialistResults: [],
        usage: { inputTokens: 0, outputTokens: 0, estimatedUsd: 0, model: null },
      };
    }
    const providerConfiguration = loadRuntimeProviderConfiguration(this.source);
    assertRuntimeProviderReady(providerConfiguration);
    const inputRate = Number(this.source.VFBIZ_AGENT_RUNTIME_INPUT_USD_PER_1M);
    const outputRate = Number(this.source.VFBIZ_AGENT_RUNTIME_OUTPUT_USD_PER_1M);
    if (!Number.isFinite(inputRate) || inputRate < 0 || !Number.isFinite(outputRate) || outputRate < 0) {
      throw new RuntimeError(
        "COST_POLICY_MISSING",
        "live provider execution requires non-negative input/output USD-per-million token rates",
      );
    }
    const agent = createOrchestratorAgent(
      request.context,
      this.models,
      this.createRuntimeTools(request),
    );
    const modelProvider = new OpenAIProvider({
      ...(providerConfiguration.apiKey ? { apiKey: providerConfiguration.apiKey } : {}),
      ...(providerConfiguration.baseUrl ? { baseURL: providerConfiguration.baseUrl } : {}),
      useResponses: providerConfiguration.apiMode === "responses",
      strictFeatureValidation: true,
    });
    const runner = new Runner({
      ...buildRunnerTraceConfiguration(request, this.traceEnabled),
      modelProvider,
    });
    const input = request.checkpointState
      ? await RunState.fromString(agent, request.checkpointState)
      : request.objective;
    if (input instanceof RunState) {
      const pending = input.getInterruptions();
      if (pending.length > 0 && (request.approvalDecisions?.length ?? 0) === 0) {
        const interruption = pending[0];
        if (!interruption) throw new RuntimeError("APPROVAL_STATE_INVALID", "checkpoint interruption disappeared");
        const payloadDigest = createHash("sha256").update(interruption.arguments ?? "{}").digest("hex");
        return {
          result: {
            status: "needs-approval",
            role: "orchestrator",
            summary: "Recovered an undecided Agents SDK tool interruption from its checkpoint.",
            artifacts: [],
            evidence: [],
            coordinationRequest: null,
            approvalRequest: {
              toolName: interruption.name ?? "unknown-tool",
              interruptionId: approvalInterruptionId(interruption),
              reason: "Tool execution still requires the canonical external human approval.",
              requestedByRole: "orchestrator",
              requiredAuthority: request.context.accountableRole,
              payloadDigest,
            },
            reviewFindings: [],
          },
          executedRoles: executedRuntimeRoles(input._generatedItems),
          specialistResults: extractSpecialistResults(input._generatedItems),
          serializedState: input.toString({ includeTracingApiKey: false }),
          usage: { inputTokens: 0, outputTokens: 0, estimatedUsd: 0, model: this.models.modelFor("orchestrator") },
        };
      }
      applyApprovalDecisions(input, request.approvalDecisions ?? []);
    }
    const priorInputTokens = input instanceof RunState ? input.usage.inputTokens : 0;
    const priorOutputTokens = input instanceof RunState ? input.usage.outputTokens : 0;
    const result = await runner.run(agent, input, {
      maxTurns: request.budget.maxTurns,
      ...(request.signal ? { signal: request.signal } : {}),
    });
    const serializedState = result.state.toString({ includeTracingApiKey: false });
    const usage = result.state.usage;
    const inputTokens = Math.max(0, usage.inputTokens - priorInputTokens);
    const outputTokens = Math.max(0, usage.outputTokens - priorOutputTokens);
    const estimatedUsd = (inputTokens * inputRate + outputTokens * outputRate) / 1_000_000;
    const executedRoles = executedRuntimeRoles(result.newItems);
    const specialistResults = extractSpecialistResults(result.newItems);
    const firstInterruption = result.interruptions[0];
    if (firstInterruption) {
      const payloadDigest = createHash("sha256")
        .update(firstInterruption.arguments ?? "{}")
        .digest("hex");
      return {
        result: {
          status: "needs-approval",
          role: "orchestrator",
          summary: "An Agents SDK tool call requires an external human approval decision.",
          artifacts: [],
          evidence: [],
          coordinationRequest: null,
          approvalRequest: {
            toolName: firstInterruption.name ?? "unknown-tool",
            interruptionId: approvalInterruptionId(firstInterruption),
            reason: "Tool execution crossed the configured human-in-the-loop boundary.",
            requestedByRole: "orchestrator",
            requiredAuthority: request.context.accountableRole,
            payloadDigest,
          },
          reviewFindings: [],
        },
        serializedState,
        executedRoles,
        specialistResults,
        usage: {
          inputTokens,
          outputTokens,
          estimatedUsd,
          model: this.models.modelFor("orchestrator"),
        },
      };
    }
    const parsed = agentResultSchema.safeParse(result.finalOutput);
    const finalResult = parsed.success && parsed.data.approvalRequest === null
      ? parsed.data
      : failedSafely(
          "orchestrator",
          parsed.success
            ? "Only an actual Agents SDK interruption may create an approval request."
            : "Agents SDK returned an invalid structured result.",
        );
    return {
      result: finalResult,
      serializedState,
      executedRoles,
      specialistResults,
      usage: {
        inputTokens,
        outputTokens,
        estimatedUsd,
        model: this.models.modelFor("orchestrator"),
      },
    };
  }

  private createRuntimeTools(request: AgentExecutionRequest): Tool<unknown>[] {
    if (!this.codingExecutor || !this.fixtureRepository) return [];
    const parameters = z.object({
      objective: z.string().min(1),
      mode: z.enum(["read-only", "workspace-write"]),
    }).strict();
    return [tool({
      name: "codex_fixture",
      description: "Ask Codex to inspect or modify only the configured isolated synthetic fixture worktree.",
      parameters,
      needsApproval: (_context, input) => Promise.resolve(input.mode === "workspace-write"),
      execute: async (input, _context, details) => {
        const operationId = details?.toolCall?.callId;
        if (!operationId) {
          throw new RuntimeError("CODEX_CALL_ID_MISSING", "Codex tool call has no stable operation identity");
        }
        return JSON.stringify(await this.codingExecutor?.execute({
          runId: request.runId,
          operationId,
          objective: input.objective,
          repositoryPath: this.fixtureRepository as string,
          allowedPaths: ["."],
          mode: input.mode,
        }));
      },
    })];
  }
}
