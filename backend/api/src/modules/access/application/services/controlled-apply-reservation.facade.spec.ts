import { createHash } from 'node:crypto';
import {
  ControlledApplyReservationConflictError,
  ControlledApplyReservationForbiddenError,
  ControlledApplyReservationValidationError,
} from '../errors/controlled-apply-reservation.errors';
import { ControlledApplyReservationFacade } from './controlled-apply-reservation.facade';
import { ControlledApplyReservationRepository } from '../ports/controlled-apply-reservation.repository';
import { ControlledApplyAuthorityVerifier } from '../ports/controlled-apply-authority-verifier';
import {
  ControlledApplyReservationAggregate,
  reservationReceiptSha256,
  type ControlledApplyReservation,
  type VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';

const digest = (value: string) =>
  createHash('sha256').update(value).digest('hex');
const future = new Date(Date.now() + 60_000);

function request(
  overrides: Partial<VerifiedControlledApplyRequest> = {},
): VerifiedControlledApplyRequest {
  const sourceEnvelopeSha256 = digest('envelope');
  const nonce = digest('nonce');
  const idempotencyKey = 'controlled-apply-test-key';
  const idempotencyKeyHash = digest(idempotencyKey);
  return {
    idempotencyKey,
    idempotencyKeyHash,
    nonce,
    pairingSha256: digest('pair'),
    sourceEnvelopeUri: `gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/${sourceEnvelopeSha256}.json#42`,
    sourceEnvelopeSha256,
    sourceEnvelopeGeneration: 42n,
    claimId: 'claim-vfbiz-0220',
    claimFencingToken: 7n,
    claimExpiresAt: future,
    requesterSubjectSha256: digest('requester'),
    approverSubjectSha256: digest('approver'),
    approvalEventId: 'approval-event-0220',
    approvalEventRevision: 3n,
    approvalEvidenceSha256: digest('approval'),
    approvalPolicyRevisionSha256: digest('policy'),
    requiredCapability: 'authorization.approval.approve',
    expiresAt: future,
    ...overrides,
  };
}

class FakeRepository extends ControlledApplyReservationRepository {
  reserve = jest.fn(() =>
    Promise.resolve({
      kind: 'reserved' as const,
      reservation: {} as ControlledApplyReservation,
    }),
  );
  complete = jest.fn();
  cancel = jest.fn();
}

class FakeAuthorityVerifier extends ControlledApplyAuthorityVerifier {
  verifyReservation = jest.fn((input: VerifiedControlledApplyRequest) =>
    Promise.resolve(input),
  );
  verifyCancellation = jest.fn(
    (
      input: Parameters<
        ControlledApplyAuthorityVerifier['verifyCancellation']
      >[0],
    ) => Promise.resolve(input),
  );
}

describe('ControlledApplyReservationFacade', () => {
  it('binds source digest and generation and hashes idempotency keys', async () => {
    const repository = new FakeRepository();
    const facade = new ControlledApplyReservationFacade(
      repository,
      new FakeAuthorityVerifier(),
    );
    await facade.reserve(request());
    expect(repository.reserve).toHaveBeenCalledTimes(1);
    await expect(
      facade.reserve(
        request({
          sourceEnvelopeUri: request().sourceEnvelopeUri.replace('#42', '#43'),
        }),
      ),
    ).rejects.toThrow(ControlledApplyReservationValidationError);
    await expect(
      facade.reserve(request({ idempotencyKeyHash: digest('different') })),
    ).rejects.toThrow(ControlledApplyReservationValidationError);
  });

  it('rejects self-approval and unauthenticated cancellation', async () => {
    const repository = new FakeRepository();
    const facade = new ControlledApplyReservationFacade(
      repository,
      new FakeAuthorityVerifier(),
    );
    await expect(
      facade.reserve(
        request({ approverSubjectSha256: request().requesterSubjectSha256 }),
      ),
    ).rejects.toThrow(ControlledApplyReservationForbiddenError);
    await expect(
      facade.cancel({
        idempotencyKeyHash: digest('key'),
        claimId: 'claim-vfbiz-0220',
        claimFencingToken: 7n,
        cancellationReceiptSha256: digest('cancel'),
        evidence: {
          actorSubjectSha256: digest('actor'),
          evidenceSha256: digest('evidence'),
          eventId: 'cancel-event',
          eventRevision: 1n,
          requiredCapability: 'authorization.approval.approve',
          verified: false as true,
        },
      }),
    ).rejects.toThrow(ControlledApplyReservationForbiddenError);
  });

  it('keeps terminal receipts immutable and fences stale completion', () => {
    const input = request();
    const reservation: ControlledApplyReservation = {
      id: 'reservation-1',
      idempotencyKeyHash: input.idempotencyKeyHash,
      nonce: input.nonce,
      pairingSha256: input.pairingSha256,
      sourceEnvelopeUri: input.sourceEnvelopeUri,
      sourceEnvelopeSha256: input.sourceEnvelopeSha256,
      sourceEnvelopeGeneration: input.sourceEnvelopeGeneration,
      claimId: input.claimId,
      claimFencingToken: input.claimFencingToken,
      requesterSubjectSha256: input.requesterSubjectSha256,
      approverSubjectSha256: input.approverSubjectSha256,
      approvalEventId: input.approvalEventId,
      approvalEventRevision: input.approvalEventRevision,
      approvalEvidenceSha256: input.approvalEvidenceSha256,
      approvalPolicyRevisionSha256: input.approvalPolicyRevisionSha256,
      reservationReceiptSha256: reservationReceiptSha256(input),
      completionReceiptSha256: null,
      cancellationReceiptSha256: null,
      cancellationEvidenceSha256: null,
      cancellationActorSubjectSha256: null,
      cancellationEventId: null,
      cancellationEventRevision: null,
      state: 'reserved',
      outcome: null,
      expiresAt: future,
      reservedAt: new Date(),
      completedAt: null,
      cancelledAt: null,
    };
    const aggregate =
      ControlledApplyReservationAggregate.fromSnapshot(reservation);
    expect(() =>
      aggregate.complete({
        idempotencyKeyHash: input.idempotencyKeyHash,
        claimId: input.claimId,
        claimFencingToken: 8n,
        completionReceiptSha256: digest('completion'),
        outcome: 'succeeded',
      }),
    ).toThrow(ControlledApplyReservationConflictError);
    const completed = aggregate.complete({
      idempotencyKeyHash: input.idempotencyKeyHash,
      claimId: input.claimId,
      claimFencingToken: input.claimFencingToken,
      completionReceiptSha256: digest('completion'),
      outcome: 'succeeded',
    });
    expect(completed.state).toBe('completed');
    expect(() =>
      aggregate.complete({
        idempotencyKeyHash: input.idempotencyKeyHash,
        claimId: input.claimId,
        claimFencingToken: input.claimFencingToken,
        completionReceiptSha256: digest('other'),
        outcome: 'failed',
      }),
    ).toThrow(ControlledApplyReservationConflictError);
  });

  it('rejects a corrupted stored reservation receipt on terminal replay', () => {
    const input = request();
    const reservation: ControlledApplyReservation = {
      id: 'reservation-corrupt',
      idempotencyKeyHash: input.idempotencyKeyHash,
      nonce: input.nonce,
      pairingSha256: input.pairingSha256,
      sourceEnvelopeUri: input.sourceEnvelopeUri,
      sourceEnvelopeSha256: input.sourceEnvelopeSha256,
      sourceEnvelopeGeneration: input.sourceEnvelopeGeneration,
      claimId: input.claimId,
      claimFencingToken: input.claimFencingToken,
      requesterSubjectSha256: input.requesterSubjectSha256,
      approverSubjectSha256: input.approverSubjectSha256,
      approvalEventId: input.approvalEventId,
      approvalEventRevision: input.approvalEventRevision,
      approvalEvidenceSha256: input.approvalEvidenceSha256,
      approvalPolicyRevisionSha256: input.approvalPolicyRevisionSha256,
      reservationReceiptSha256: digest('corrupt-receipt'),
      completionReceiptSha256: digest('completion'),
      cancellationReceiptSha256: null,
      cancellationEvidenceSha256: null,
      cancellationActorSubjectSha256: null,
      cancellationEventId: null,
      cancellationEventRevision: null,
      state: 'completed',
      outcome: 'succeeded',
      expiresAt: future,
      reservedAt: new Date(),
      completedAt: new Date(),
      cancelledAt: null,
    };
    const aggregate =
      ControlledApplyReservationAggregate.fromSnapshot(reservation);
    expect(() =>
      aggregate.complete({
        idempotencyKeyHash: input.idempotencyKeyHash,
        claimId: input.claimId,
        claimFencingToken: input.claimFencingToken,
        completionReceiptSha256: reservation.completionReceiptSha256!,
        outcome: 'succeeded',
      }),
    ).toThrow(ControlledApplyReservationConflictError);
    const reserved = {
      ...reservation,
      state: 'reserved' as const,
      completionReceiptSha256: null,
      completedAt: null,
    };
    expect(() =>
      ControlledApplyReservationAggregate.fromSnapshot(reserved).cancel({
        idempotencyKeyHash: input.idempotencyKeyHash,
        claimId: input.claimId,
        claimFencingToken: input.claimFencingToken,
        cancellationReceiptSha256: digest('cancel'),
        evidence: {
          actorSubjectSha256: digest('actor'),
          evidenceSha256: digest('cancel-evidence'),
          eventId: 'cancel-event-0220',
          eventRevision: 1n,
          requiredCapability: 'authorization.approval.approve',
          verified: true,
        },
      }),
    ).toThrow(ControlledApplyReservationConflictError);
  });
});
