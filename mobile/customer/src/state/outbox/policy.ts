export type MutationRisk = "low" | "privileged";

export function canQueueOfflineMutation(input: {
  online: boolean;
  risk: MutationRisk;
  idempotencyKey?: string;
  etagRequired?: boolean;
  etag?: string;
}): boolean {
  if (input.online) return true;
  if (input.risk !== "low" || !input.idempotencyKey) return false;
  if (input.etagRequired && !input.etag) return false;
  return true;
}
