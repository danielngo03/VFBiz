import { z } from "zod";

export const artifactReferenceSchema = z.object({
  kind: z.enum(["decision-packet", "worker-report", "review-finding", "evidence", "sandbox-output"]),
  path: z.string().min(1),
  sha256: z.string().regex(/^[a-f0-9]{64}$/),
  mediaType: z.string().min(1),
}).strict();

export const coordinationRequestSchema = z.object({
  targetTeam: z.string().min(1),
  reason: z.string().min(1),
  requiredAuthority: z.string().min(1).nullable(),
}).strict();

export const approvalRequestSchema = z.object({
  toolName: z.string().min(1),
  interruptionId: z.string().min(1),
  reason: z.string().min(1),
  requestedByRole: z.enum(["orchestrator", "explorer", "implementer", "reviewer-verifier", "risk-reviewer", "integrator"]),
  requiredAuthority: z.string().min(1),
  payloadDigest: z.string().regex(/^[a-f0-9]{64}$/),
}).strict();

export const reviewFindingSchema = z.object({
  fingerprint: z.string().regex(/^[a-f0-9]{64}$/),
  severity: z.enum(["P0", "P1", "P2", "P3"]),
  summary: z.string().min(1),
  evidence: z.string().min(1),
}).strict();

export const agentResultSchema = z.object({
  status: z.enum(["completed", "needs-approval", "needs-decision", "failed-safely"]),
  role: z.enum(["orchestrator", "explorer", "implementer", "reviewer-verifier", "risk-reviewer", "integrator"]),
  summary: z.string().min(1),
  artifacts: z.array(artifactReferenceSchema),
  evidence: z.array(z.string()),
  coordinationRequest: coordinationRequestSchema.nullable(),
  approvalRequest: approvalRequestSchema.nullable(),
  reviewFindings: z.array(reviewFindingSchema),
}).strict();

export type AgentResult = z.infer<typeof agentResultSchema>;

export function failedSafely(role: AgentResult["role"], summary: string): AgentResult {
  return {
    status: "failed-safely",
    role,
    summary,
    artifacts: [],
    evidence: [],
    coordinationRequest: null,
    approvalRequest: null,
    reviewFindings: [],
  };
}
