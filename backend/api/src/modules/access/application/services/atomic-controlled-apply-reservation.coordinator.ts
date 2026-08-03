import {
  ControlledApplyReservationAuthorityUnavailableError,
  ControlledApplyReservationConflictError,
  ControlledApplyReservationValidationError,
} from '../errors/controlled-apply-reservation.errors';
import { ControlledApplyAtomicReservationStore } from '../ports/controlled-apply-atomic-reservation';
import { ControlledApplySourceEnvelopeIntegrity } from '../ports/controlled-apply-source-envelope-integrity';
import {
  assertVerifiedControlledApplyRequest,
  type ControlledApplyReservationResult,
  type VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';

/**
 * Candidate coordinator for the future API-owned authority implementation.
 *
 * Source bytes are verified before opening the database transaction, then the
 * approval/claim join is read again by the transaction-bound store immediately
 * before the nonce reservation. The class is intentionally not registered in
 * `AccessModule`: no workforce-backed transaction store exists yet and the
 * production facade remains fail-closed.
 */
export class AtomicControlledApplyReservationCoordinator {
  constructor(
    private readonly sourceIntegrity: ControlledApplySourceEnvelopeIntegrity,
    private readonly store: ControlledApplyAtomicReservationStore,
  ) {}

  async reserve(
    input: VerifiedControlledApplyRequest,
  ): Promise<ControlledApplyReservationResult> {
    assertVerifiedControlledApplyRequest(input);
    await this.assertSourceEnvelope(input);

    return this.store.withSerializable(async (transaction) => {
      const join = await transaction.readReservationAuthorityJoin(input);
      if (join === null) {
        throw new ControlledApplyReservationAuthorityUnavailableError(
          'transaction-scoped workforce/approval authority join is unavailable',
        );
      }
      assertReservationJoinForTransaction(input, join);
      return transaction.reserve(input);
    });
  }

  private async assertSourceEnvelope(
    input: VerifiedControlledApplyRequest,
  ): Promise<void> {
    try {
      await this.sourceIntegrity.assertExact(input);
    } catch (error) {
      if (
        error instanceof ControlledApplyReservationConflictError ||
        error instanceof ControlledApplyReservationValidationError
      ) {
        throw error;
      }
      throw new ControlledApplyReservationAuthorityUnavailableError(
        'exact source envelope could not be verified',
      );
    }
  }
}

function assertReservationJoinForTransaction(
  input: VerifiedControlledApplyRequest,
  join: {
    readonly claimId: string;
    readonly claimFencingToken: bigint;
    readonly claimExpiresAt: Date;
    readonly requesterSubjectSha256: string;
    readonly approverSubjectSha256: string;
    readonly approvalEventId: string;
    readonly approvalEventRevision: bigint;
    readonly approvalEvidenceSha256: string;
    readonly approvalPolicyRevisionSha256: string;
    readonly requiredCapability: 'authorization.approval.approve';
    readonly approvalState: 'approved';
    readonly cancelledAt: Date | null;
  },
): void {
  if (
    join.approvalState !== 'approved' ||
    join.cancelledAt !== null ||
    !(join.claimExpiresAt instanceof Date) ||
    !Number.isFinite(join.claimExpiresAt.getTime()) ||
    join.claimExpiresAt.getTime() <= Date.now() ||
    join.requiredCapability !== input.requiredCapability ||
    join.claimId !== input.claimId ||
    join.claimFencingToken !== input.claimFencingToken ||
    join.claimExpiresAt.getTime() !== input.claimExpiresAt.getTime() ||
    join.requesterSubjectSha256 !== input.requesterSubjectSha256 ||
    join.approverSubjectSha256 !== input.approverSubjectSha256 ||
    join.requesterSubjectSha256 === join.approverSubjectSha256 ||
    join.approvalEventId !== input.approvalEventId ||
    join.approvalEventRevision !== input.approvalEventRevision ||
    join.approvalEvidenceSha256 !== input.approvalEvidenceSha256 ||
    join.approvalPolicyRevisionSha256 !== input.approvalPolicyRevisionSha256
  ) {
    throw new ControlledApplyReservationConflictError(
      'transaction-scoped workforce/approval join does not match the signed claim',
    );
  }
}
