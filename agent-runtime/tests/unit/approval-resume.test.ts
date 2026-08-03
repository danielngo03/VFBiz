import { createHash } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import {
  applyApprovalDecisions,
  extractSpecialistResults,
} from "../../src/adapters/openai/agents-sdk-executor.js";

describe("Agents SDK approval resume", () => {
  it("applies the persisted decision to the exact interrupted payload", () => {
    const interruption = {
      name: "ask_implementer",
      arguments: '{"input":"fixture"}',
      rawItem: { callId: "call-fixture-1" },
    };
    const approve = vi.fn();
    const state = {
      getInterruptions: () => [interruption],
      approve,
      reject: vi.fn(),
    };
    applyApprovalDecisions(state, [{
      toolName: interruption.name,
      interruptionId: interruption.rawItem.callId,
      payloadDigest: createHash("sha256").update(interruption.arguments).digest("hex"),
      decision: "approved",
      reason: "Fixture execution authorized",
    }]);
    expect(approve).toHaveBeenCalledWith(interruption);
  });

  it("blocks replay against a different payload digest", () => {
    const interruption = {
      name: "ask_implementer",
      arguments: '{"input":"changed"}',
      rawItem: { callId: "call-fixture-2" },
    };
    const state = {
      getInterruptions: () => [interruption],
      approve: vi.fn(),
      reject: vi.fn(),
    };
    expect(() => applyApprovalDecisions(state, [{
      toolName: interruption.name,
      interruptionId: interruption.rawItem.callId,
      payloadDigest: "c".repeat(64),
      decision: "approved",
      reason: "stale decision",
    }])).toThrow(/undecided/);
  });

  it("blocks reuse for a later call with identical arguments", () => {
    const interruption = {
      name: "ask_implementer",
      arguments: '{"input":"same"}',
      rawItem: { callId: "call-later" },
    };
    const state = {
      getInterruptions: () => [interruption],
      approve: vi.fn(),
      reject: vi.fn(),
    };
    expect(() => applyApprovalDecisions(state, [{
      toolName: interruption.name,
      interruptionId: "call-earlier",
      payloadDigest: createHash("sha256").update(interruption.arguments).digest("hex"),
      decision: "approved",
      reason: "earlier call only",
    }])).toThrow(/undecided/);
  });

  it("recognizes a reviewer only from its completed typed specialist output", () => {
    const reviewer = {
      status: "completed",
      role: "reviewer-verifier",
      summary: "Independent fixture review",
      artifacts: [],
      evidence: ["fixture:test"],
      coordinationRequest: null,
      approvalRequest: null,
      reviewFindings: [],
    };
    expect(extractSpecialistResults([{
      rawItem: {
        type: "function_call_result",
        name: "ask_reviewer_verifier",
        output: { type: "text", text: JSON.stringify(reviewer) },
      },
    }])).toEqual([reviewer]);
    expect(extractSpecialistResults([{
      rawItem: {
        type: "function_call",
        name: "ask_reviewer_verifier",
      },
    }])).toEqual([]);
  });
});
