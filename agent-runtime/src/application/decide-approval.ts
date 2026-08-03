import type { ApprovalDecision, RuntimeApproval } from "../domain/approval-decision.js";
import { RuntimeError } from "../domain/errors.js";
import type { RunStore } from "../ports/run-store.js";

export function decideApproval(decision: ApprovalDecision, store: RunStore): RuntimeApproval {
  const approval = store.getApproval(decision.approvalId);
  if (!approval) throw new RuntimeError("APPROVAL_NOT_FOUND", `approval not found: ${decision.approvalId}`);
  if (decision.decidedBy !== `human:${approval.requiredAuthority}`) {
    throw new RuntimeError(
      "APPROVAL_AUTHORITY_MISMATCH",
      `approval requires human:${approval.requiredAuthority}`,
    );
  }
  return store.decideApproval(decision);
}
