import {
  ControlledApplyReservationAuthorityUnavailableError,
  ControlledApplyReservationConflictError,
  ControlledApplyReservationValidationError,
} from '../../application/errors/controlled-apply-reservation.errors';
import { ControlledApplyAuthorityJoinReader } from '../../application/ports/controlled-apply-authority-join-reader';
import type {
  ControlledApplyCancellationAuthorityJoin,
  ControlledApplyReservationAuthorityJoin,
} from '../../application/ports/controlled-apply-authority-join-reader';
import type { ControlledApplySourceEnvelopeReader } from '../../application/ports/controlled-apply-source-envelope-reader';
import {
  assertCancellationEvidence,
  assertVerifiedControlledApplyRequest,
  type CancelControlledApplyRequest,
  type VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';
import { assertExactSourceEnvelopeIntegrity } from './exact-source-envelope-integrity';

/**
 * Candidate preflight that composes both API-owned evidence boundaries.
 *
 * This class deliberately does not implement `ControlledApplyAuthorityVerifier`
 * and does not return a verified request. That prevents a caller from reading
 * source/join state and then handing a stale result to the separate reservation
 * transaction. A future production implementation must perform source
 * verification, authoritative join lookup and nonce reservation in one
 * serializable transaction (or re-check the join inside that transaction).
 */
export class SourceAwareControlledApplyAuthorityPreflight {
  constructor(
    private readonly sourceReader: ControlledApplySourceEnvelopeReader,
    private readonly joinReader: ControlledApplyAuthorityJoinReader,
  ) {}

  async assertReservationPreflight(
    input: VerifiedControlledApplyRequest,
  ): Promise<void> {
    assertVerifiedControlledApplyRequest(input);
    await this.assertSourceEnvelope(input);

    const join = await this.readReservationJoin(input);
    if (join === null) {
      throw new ControlledApplyReservationAuthorityUnavailableError(
        'API workforce/approval authority join is unavailable',
      );
    }
    assertReservationJoinMatches(input, join);
  }

  async assertCancellationPreflight(
    input: CancelControlledApplyRequest,
  ): Promise<void> {
    assertCancellationEvidence(input.evidence);

    const join = await this.readCancellationJoin(input);
    if (join === null) {
      throw new ControlledApplyReservationAuthorityUnavailableError(
        'API cancellation authority join is unavailable',
      );
    }
    assertCancellationJoinMatches(input, join);
  }

  private async assertSourceEnvelope(
    input: VerifiedControlledApplyRequest,
  ): Promise<void> {
    try {
      await assertExactSourceEnvelopeIntegrity(this.sourceReader, input);
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

  private async readReservationJoin(input: VerifiedControlledApplyRequest) {
    try {
      return await this.joinReader.readReservationJoin(input);
    } catch (error) {
      void error;
      throw new ControlledApplyReservationAuthorityUnavailableError(
        'API workforce/approval authority join could not be read',
      );
    }
  }

  private async readCancellationJoin(input: CancelControlledApplyRequest) {
    try {
      return await this.joinReader.readCancellationJoin(input);
    } catch (error) {
      void error;
      throw new ControlledApplyReservationAuthorityUnavailableError(
        'API cancellation authority join could not be read',
      );
    }
  }
}

function assertReservationJoinMatches(
  input: VerifiedControlledApplyRequest,
  join: ControlledApplyReservationAuthorityJoin,
): void {
  if (
    join.approvalState !== 'approved' ||
    join.cancelledAt !== null ||
    !(join.claimExpiresAt instanceof Date) ||
    !Number.isFinite(join.claimExpiresAt.getTime()) ||
    join.requiredCapability !== input.requiredCapability ||
    join.claimId !== input.claimId ||
    join.claimFencingToken !== input.claimFencingToken ||
    join.claimExpiresAt.getTime() !== input.claimExpiresAt.getTime() ||
    join.requesterSubjectSha256 !== input.requesterSubjectSha256 ||
    join.approverSubjectSha256 !== input.approverSubjectSha256 ||
    join.approvalEventId !== input.approvalEventId ||
    join.approvalEventRevision !== input.approvalEventRevision ||
    join.approvalEvidenceSha256 !== input.approvalEvidenceSha256 ||
    join.approvalPolicyRevisionSha256 !== input.approvalPolicyRevisionSha256
  ) {
    throw new ControlledApplyReservationConflictError(
      'API workforce/approval authority join does not match the signed claim',
    );
  }
}

function assertCancellationJoinMatches(
  input: CancelControlledApplyRequest,
  join: ControlledApplyCancellationAuthorityJoin,
): void {
  if (
    join.verified !== true ||
    join.requiredCapability !== input.evidence.requiredCapability ||
    join.idempotencyKeyHash !== input.idempotencyKeyHash ||
    join.claimId !== input.claimId ||
    join.claimFencingToken !== input.claimFencingToken ||
    join.actorSubjectSha256 !== input.evidence.actorSubjectSha256 ||
    join.evidenceSha256 !== input.evidence.evidenceSha256 ||
    join.eventId !== input.evidence.eventId ||
    join.eventRevision !== input.evidence.eventRevision
  ) {
    throw new ControlledApplyReservationConflictError(
      'API cancellation authority join does not match the cancellation evidence',
    );
  }
}
