import type { VerifiedControlledApplyRequest } from '../../domain/controlled-apply-reservation';

/**
 * Application-facing source-integrity port. Infrastructure adapters must
 * fetch one exact object generation and independently rehash its bytes before
 * this method resolves; application services must not import provider code.
 */
export abstract class ControlledApplySourceEnvelopeIntegrity {
  abstract assertExact(input: VerifiedControlledApplyRequest): Promise<void>;
}
