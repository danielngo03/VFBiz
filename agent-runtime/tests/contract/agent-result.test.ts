import { describe, expect, it } from "vitest";
import { agentResultSchema } from "../../src/agents/agent-result.js";

const valid = {
  status: "completed",
  role: "orchestrator",
  summary: "Synthetic work completed.",
  artifacts: [],
  evidence: ["fixture:test"],
  coordinationRequest: null,
  approvalRequest: null,
  reviewFindings: [],
};

describe("AgentResult contract", () => {
  it("accepts the typed boundary", () => {
    expect(agentResultSchema.safeParse(valid).success).toBe(true);
  });

  it("rejects invented agents and untyped authority", () => {
    expect(agentResultSchema.safeParse({ ...valid, role: "chief-autonomous-officer" }).success).toBe(false);
    expect(agentResultSchema.safeParse({ ...valid, approved: true }).success).toBe(false);
  });
});
