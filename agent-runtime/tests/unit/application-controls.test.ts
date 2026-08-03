import { describe, expect, it } from "vitest";
import { SqliteRunStore } from "../../src/adapters/persistence/sqlite/sqlite-run-store.js";
import { StateCipher } from "../../src/adapters/persistence/sqlite/state-cipher.js";
import { enqueueRun } from "../../src/application/enqueue-run.js";
import { executeRun } from "../../src/application/execute-run.js";
import type { AgentResult } from "../../src/agents/agent-result.js";
import type { AgentExecutor } from "../../src/ports/agent-executor.js";
import type {
  ExecutionAuthority,
  GovernanceGateway,
  ResolvedRuntimeContext,
} from "../../src/ports/governance-gateway.js";
import { enqueueInput, testStateKey } from "../helpers.js";

const context: ResolvedRuntimeContext = {
  contextKey: "a".repeat(64),
  workItemKey: "VFBIZ-0204",
  workItemRevision: 5,
  workspace: "agent-runtime",
  ownerTeam: "agent-platform",
  ownerDepartment: "engineering-enablement",
  accountableRole: "engineering-lead",
  mode: "controlled",
  allowedPaths: ["agent-runtime"],
  requiredAuthorities: ["architect", "security-owner"],
  requiredReviewers: ["reviewer-verifier", "risk-reviewer"],
  registeredTeams: ["agent-platform", "platform-security"],
  registeredAuthorities: ["engineering-lead", "architect", "security-owner"],
  claimRequired: true,
  baseRevision: "731ba5f459eada0ac9af52b179c74f8e6696d40d",
};

class FakeGovernance implements GovernanceGateway {
  public authorities: Array<ExecutionAuthority | null> = [];
  public freshChecks = 0;
  public rejectFresh = false;

  public resolve(): Promise<ResolvedRuntimeContext> {
    return Promise.resolve(context);
  }

  public assertFresh(): Promise<void> {
    this.freshChecks += 1;
    if (this.rejectFresh) throw new Error("canonical context changed");
    return Promise.resolve();
  }

  public assertExecutionAuthority(
    _context: ResolvedRuntimeContext,
    authority: ExecutionAuthority | null,
  ): Promise<void> {
    this.authorities.push(authority);
    if (!authority) throw new Error("claim required");
    return Promise.resolve();
  }

  public verifyArtifact(): Promise<void> {
    return Promise.resolve();
  }
}

function completedResult(overrides: Partial<AgentResult> = {}): AgentResult {
  return {
    status: "completed",
    role: "orchestrator",
    summary: "Synthetic controlled fixture task completed",
    artifacts: [],
    evidence: ["synthetic"],
    coordinationRequest: null,
    approvalRequest: null,
    reviewFindings: [],
    ...overrides,
  };
}

function fakeExecutor(
  result: AgentResult,
  options: { cancel?: (runId: string) => void; inputTokens?: number; estimatedUsd?: number } = {},
): AgentExecutor {
  return {
    execute: (request) => {
      options.cancel?.(request.runId);
      return Promise.resolve({
        result,
        executedRoles: ["orchestrator", "reviewer-verifier", "risk-reviewer"],
        specialistResults: [
          completedResult({ role: "reviewer-verifier" }),
          completedResult({ role: "risk-reviewer" }),
        ],
        usage: {
          inputTokens: options.inputTokens ?? 10,
          outputTokens: 5,
          estimatedUsd: options.estimatedUsd ?? 0.01,
          model: "fixture-model",
        },
      });
    },
  };
}

function runningStore() {
  const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
  store.initialize();
  const queued = store.enqueue(enqueueInput());
  const run = store.claimNextRun("worker-fixture");
  if (!run || run.id !== queued.id) throw new Error("fixture run was not claimed");
  return { store, run };
}

describe("application control enforcement", () => {
  it("rejects caller mode downgrade and missing canonical claim", async () => {
    const store = new SqliteRunStore(":memory:", () => new StateCipher(testStateKey));
    store.initialize();
    const governance = new FakeGovernance();
    await expect(enqueueRun({
      workItemKey: "VFBIZ-0204",
      targetPath: "agent-runtime",
      mode: "discovery",
    }, store, governance)).rejects.toMatchObject({ code: "MODE_OVERRIDE_REJECTED" });
    await expect(enqueueRun({
      workItemKey: "VFBIZ-0204",
      targetPath: "agent-runtime",
    }, store, governance)).rejects.toThrow(/claim required/);
    store.close();
  });

  it("fails safely on invented authority and missing independent reviewers", async () => {
    const first = runningStore();
    const governance = new FakeGovernance();
    const invented = completedResult({
      status: "needs-approval",
      approvalRequest: {
        toolName: "codex_fixture",
        interruptionId: "call-invented",
        reason: "invented",
        requestedByRole: "orchestrator",
        requiredAuthority: "robot-ceo",
        payloadDigest: "b".repeat(64),
      },
    });
    expect((await executeRun(first.run.id, first.store, governance, fakeExecutor(invented))).failureCode)
      .toBe("UNKNOWN_APPROVAL_AUTHORITY");
    first.store.close();

    const second = runningStore();
    const noReviewExecutor: AgentExecutor = {
      execute: () => Promise.resolve({
        result: completedResult(),
        executedRoles: ["orchestrator"],
        specialistResults: [],
        usage: { inputTokens: 10, outputTokens: 5, estimatedUsd: 0.01, model: "fixture-model" },
      }),
    };
    expect((await executeRun(second.run.id, second.store, governance, noReviewExecutor)).failureCode)
      .toBe("REQUIRED_REVIEW_MISSING");
    second.store.close();
  });

  it("enforces cumulative budgets and cancellation even when an executor ignores abort", async () => {
    const overBudget = runningStore();
    expect((await executeRun(
      overBudget.run.id,
      overBudget.store,
      new FakeGovernance(),
      fakeExecutor(completedResult(), { inputTokens: 100_001 }),
    )).failureCode).toBe("RUNTIME_BUDGET_EXCEEDED");
    overBudget.store.close();

    const cancelled = runningStore();
    expect((await executeRun(
      cancelled.run.id,
      cancelled.store,
      new FakeGovernance(),
      fakeExecutor(completedResult(), { cancel: (runId) => { cancelled.store.requestCancellation(runId); } }),
    )).state).toBe("cancelled");
    cancelled.store.close();
  });

  it("refreshes canonical context and claim after provider execution", async () => {
    const fixture = runningStore();
    const governance = new FakeGovernance();
    const result = await executeRun(
      fixture.run.id,
      fixture.store,
      governance,
      fakeExecutor(completedResult()),
    );
    expect(result.state).toBe("succeeded");
    expect(governance.freshChecks).toBe(1);
    expect(governance.authorities).toHaveLength(2);
    fixture.store.close();
  });

  it("fails safely when canonical authority changes during provider execution", async () => {
    const fixture = runningStore();
    const governance = new FakeGovernance();
    governance.rejectFresh = true;
    const result = await executeRun(
      fixture.run.id,
      fixture.store,
      governance,
      fakeExecutor(completedResult()),
    );
    expect(result).toMatchObject({ state: "failed_safely", failureCode: "GOVERNANCE_REFRESH_FAILED" });
    fixture.store.close();
  });

  it("recreates an idempotent approval after a crash immediately after checkpoint persistence", async () => {
    const fixture = runningStore();
    const approvalResult = completedResult({
      status: "needs-approval",
      approvalRequest: {
        toolName: "codex_fixture",
        interruptionId: "call-recovered",
        reason: "fixture write",
        requestedByRole: "orchestrator",
        requiredAuthority: "engineering-lead",
        payloadDigest: "c".repeat(64),
      },
    });
    const interruptedExecutor: AgentExecutor = {
      execute: () => Promise.resolve({
        result: approvalResult,
        executedRoles: ["orchestrator"],
        specialistResults: [],
        serializedState: "serialized-interruption",
        usage: { inputTokens: 10, outputTokens: 5, estimatedUsd: 0.01, model: "fixture-model" },
      }),
    };
    const originalRecordUsage = fixture.store.recordUsage.bind(fixture.store);
    let crashOnce = true;
    fixture.store.recordUsage = (runId, usage, idempotencyKey) => {
      if (crashOnce) {
        crashOnce = false;
        throw new Error("synthetic crash after checkpoint");
      }
      originalRecordUsage(runId, usage, idempotencyKey);
    };
    await expect(executeRun(fixture.run.id, fixture.store, new FakeGovernance(), interruptedExecutor))
      .rejects.toThrow(/synthetic crash/);
    expect(fixture.store.getLatestCheckpoint(fixture.run.id)).not.toBeNull();
    expect(fixture.store.listApprovals()).toHaveLength(0);
    fixture.store.reconcileStale("9999-12-31T23:59:59.999Z");
    expect(fixture.store.claimNextRun("worker-after-restart")?.id).toBe(fixture.run.id);
    const recovered = await executeRun(
      fixture.run.id,
      fixture.store,
      new FakeGovernance(),
      {
        execute: (request) => {
          expect(request.checkpointState).toBe("serialized-interruption");
          return Promise.resolve({
            result: approvalResult,
            executedRoles: ["orchestrator"],
            specialistResults: [],
            serializedState: "serialized-interruption",
            usage: { inputTokens: 0, outputTokens: 0, estimatedUsd: 0, model: "fixture-model" },
          });
        },
      },
    );
    expect(recovered.state).toBe("waiting_approval");
    expect(fixture.store.listApprovals()).toHaveLength(1);
    fixture.store.close();
  });
});
