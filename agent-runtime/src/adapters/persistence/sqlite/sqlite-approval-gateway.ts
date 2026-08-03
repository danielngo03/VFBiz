import type { ApprovalDecision, RuntimeApproval } from "../../../domain/approval-decision.js";
import type { ApprovalGateway } from "../../../ports/approval-gateway.js";
import type { RunStore } from "../../../ports/run-store.js";

export class SqliteApprovalGateway implements ApprovalGateway {
  public constructor(private readonly store: RunStore) {}

  public request(
    input: Omit<RuntimeApproval, "id" | "status" | "decidedBy" | "decisionReason" | "requestedAt" | "decidedAt">,
  ): RuntimeApproval {
    return this.store.createApproval(input);
  }

  public decide(decision: ApprovalDecision): RuntimeApproval {
    return this.store.decideApproval(decision);
  }

  public list(status?: RuntimeApproval["status"]): RuntimeApproval[] {
    return this.store.listApprovals(status);
  }
}
