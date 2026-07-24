export interface SessionMutationResult {
  readonly message: string;
  readonly ok: boolean;
  readonly reconciliation?:
    | "confirmed"
    | "manual_review_required"
    | "pending"
    | "retry_required";
}
