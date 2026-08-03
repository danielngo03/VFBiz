export const approvalStatuses = ["pending", "approved", "rejected"] as const;
export type ApprovalStatus = (typeof approvalStatuses)[number];

export interface RuntimeApproval {
  id: string;
  runId: string;
  toolName: string;
  interruptionId: string;
  reason: string;
  requestedByRole: string;
  requiredAuthority: string;
  payloadDigest: string;
  status: ApprovalStatus;
  decidedBy: string | null;
  decisionReason: string | null;
  requestedAt: string;
  decidedAt: string | null;
}

export interface ApprovalDecision {
  approvalId: string;
  decision: "approved" | "rejected";
  decidedBy: string;
  reason: string;
}
