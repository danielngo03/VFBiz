export type IdempotencyReservation =
  | { readonly kind: 'reserved' }
  | {
      readonly kind: 'replay';
      readonly responseStatus: number;
      readonly responseBody: unknown;
    }
  | { readonly kind: 'conflict' };

export interface ReserveIdempotencyKeyInput {
  readonly namespace: string;
  readonly key: string;
  readonly requestHash: string;
  readonly ttlSeconds: number;
}

export interface CompleteIdempotencyKeyInput {
  readonly namespace: string;
  readonly key: string;
  readonly responseStatus: number;
  readonly responseBody: unknown;
}

/**
 * Namespace scopes one Idempotency-Key header value to one logical
 * operation (e.g. "workforce.role.create") so the same header value reused
 * across unrelated endpoints cannot collide. requestHash additionally binds
 * the key to one specific request payload: replaying the exact request
 * returns the cached response; reusing the key for a different request (or
 * a request still in flight) is a conflict, never a silent pass-through.
 */
export abstract class IdempotencyRepository {
  abstract reserve(
    input: ReserveIdempotencyKeyInput,
  ): Promise<IdempotencyReservation>;

  abstract complete(input: CompleteIdempotencyKeyInput): Promise<void>;
}
