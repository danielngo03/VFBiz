import type {
  ControlledApplyReservationResult,
  VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';
import type { ControlledApplyReservationAuthorityJoin } from './controlled-apply-authority-join-reader';

/**
 * Transaction-scoped read/write surface for the future workforce-backed
 * reservation aggregate. The join and reservation write must use the same
 * serializable transaction; a preflight result is never accepted as proof.
 */
export interface ControlledApplyAtomicReservationTransaction {
  readReservationAuthorityJoin(
    input: VerifiedControlledApplyRequest,
  ): Promise<ControlledApplyReservationAuthorityJoin | null>;

  reserve(
    input: VerifiedControlledApplyRequest,
  ): Promise<ControlledApplyReservationResult>;
}

/**
 * Internal-only store boundary. A concrete Prisma implementation must keep the
 * transaction callback on one connection and retry only serialization
 * failures. It must not expose the transaction client to HTTP or provider
 * adapters.
 */
export abstract class ControlledApplyAtomicReservationStore {
  abstract withSerializable<T>(
    operation: (
      transaction: ControlledApplyAtomicReservationTransaction,
    ) => Promise<T>,
  ): Promise<T>;
}
