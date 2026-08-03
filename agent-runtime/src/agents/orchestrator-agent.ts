import { Agent, type Tool } from "@openai/agents";
import type { ModelPolicy, RuntimeRole } from "../config/model-policy.js";
import type { ResolvedRuntimeContext } from "../ports/governance-gateway.js";
import { agentResultSchema } from "./agent-result.js";
import { instructionsFor } from "./instructions.js";
import { createRoleAgent } from "./role-agent-factory.js";

const specialistRoles: readonly RuntimeRole[] = [
  "explorer",
  "implementer",
  "reviewer-verifier",
  "risk-reviewer",
  "integrator",
];

export function createOrchestratorAgent(
  context: ResolvedRuntimeContext,
  models: ModelPolicy,
  runtimeTools: Tool<unknown>[] = [],
): Agent<unknown, typeof agentResultSchema> {
  const tools = specialistRoles.map((role) => {
    const specialist = createRoleAgent(role, context, models);
    return specialist.asTool({
      toolName: `ask_${role.replaceAll("-", "_")}`,
      toolDescription: `Ask the registered ${role} for a bounded typed result.`,
      needsApproval:
        context.mode === "controlled" &&
        (role === "implementer" || role === "integrator"),
      customOutputExtractor: (result) => JSON.stringify(result.finalOutput),
    });
  });
  return new Agent({
    name: "orchestrator",
    model: models.modelFor("orchestrator"),
    instructions: instructionsFor("orchestrator", context),
    tools: [...tools, ...runtimeTools],
    outputType: agentResultSchema,
  });
}
