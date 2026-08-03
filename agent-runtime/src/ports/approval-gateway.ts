import type { ApprovalDecision, RuntimeApproval } from "../domain/approval-decision.js";

export interface ApprovalGateway {
  request(input: Omit<RuntimeApproval, "id" | "status" | "decidedBy" | "decisionReason" | "requestedAt" | "decidedAt">): RuntimeApproval;
  decide(decision: ApprovalDecision): RuntimeApproval;
  list(status?: RuntimeApproval["status"]): RuntimeApproval[];
}
