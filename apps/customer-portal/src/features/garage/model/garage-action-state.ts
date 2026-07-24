export type GarageActionCode =
  | "completed"
  | "conflict"
  | "forbidden"
  | "invalid"
  | "invalid_variant"
  | "not_found"
  | "provider_unavailable"
  | "session_required"
  | "stale_catalog"
  | "unexpected";

export interface GarageActionState {
  readonly code: GarageActionCode;
  readonly correlationId?: string;
  readonly message: string;
}

export const INITIAL_GARAGE_ACTION_STATE: GarageActionState = Object.freeze({
  code: "completed",
  message: "",
});

export function garageCreateIdempotencyKey(requestId: string): string {
  return `garage:${requestId}`;
}
