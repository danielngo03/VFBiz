import { Agent } from "@openai/agents";
import type { ModelPolicy, RuntimeRole } from "../config/model-policy.js";
import type { ResolvedRuntimeContext } from "../ports/governance-gateway.js";
import { agentResultSchema } from "./agent-result.js";
import { instructionsFor } from "./instructions.js";

export const runtimeRoles: readonly RuntimeRole[] = [
  "orchestrator",
  "explorer",
  "implementer",
  "reviewer-verifier",
  "risk-reviewer",
  "integrator",
];

export function createRoleAgent(
  role: RuntimeRole,
  context: ResolvedRuntimeContext,
  models: ModelPolicy,
): Agent<unknown, typeof agentResultSchema> {
  return new Agent({
    name: role,
    model: models.modelFor(role),
    instructions: instructionsFor(role, context),
    outputType: agentResultSchema,
  });
}
