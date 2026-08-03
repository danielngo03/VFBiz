import { describe, expect, it } from "vitest";
import { buildCodexToolArguments } from "../../src/adapters/codex/codex-mcp-executor.js";
import { boundedWorkflow } from "../../src/workflows/bounded-workflow.js";
import { controlledWorkflow } from "../../src/workflows/controlled-workflow.js";

describe("workflow contracts", () => {
  it("places independent reviews after implementation", () => {
    expect(controlledWorkflow.stages.indexOf("reviewer-verifier")).toBeGreaterThan(
      controlledWorkflow.stages.indexOf("implementer"),
    );
    expect(controlledWorkflow.stages.indexOf("risk-reviewer")).toBeGreaterThan(
      controlledWorkflow.stages.indexOf("implementer"),
    );
    expect(boundedWorkflow.requiredReviewers).toEqual(["reviewer-verifier"]);
  });

  it("pins Codex to never-approve and disables nested delegation", () => {
    const args = buildCodexToolArguments({
      runId: "run-fixture",
      operationId: "call-fixture",
      objective: "Inspect fixture",
      repositoryPath: "/tmp/fixture",
      allowedPaths: ["src"],
      mode: "read-only",
    });
    expect(args["approval-policy"]).toBe("never");
    expect(args.sandbox).toBe("read-only");
    expect(args.prompt).toContain("Do not spawn or delegate to nested agents");
    expect(args["developer-instructions"]).toContain("Nested agents and delegation are disabled");
  });
});
