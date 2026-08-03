import { createHash } from 'node:crypto';
import {
  ControlledApplyReservationConflictError,
  ControlledApplyReservationForbiddenError,
  ControlledApplyReservationValidationError,
} from '../application/errors/controlled-apply-reservation.errors';

const SHA256 = /^[a-f0-9]{64}$/;
const CLAIM_ID = /^[a-zA-Z0-9._:/-]{8,256}$/;
const URI =
  /^gs:\/\/vinfast-503003-evidence-dev\/controlled-apply\/authority-envelopes\/v1\/([a-f0-9]{64})\.json#([1-9][0-9]*)$/;
const CAPABILITY = 'authorization.approval.approve';

export type ControlledApplyReservationState =
  'reserved' | 'completed' | 'cancelled';

export interface VerifiedControlledApplyRequest {
  readonly idempotencyKey: string;
  readonly idempotencyKeyHash: string;
  readonly nonce: string;
  readonly pairingSha256: string;
  readonly sourceEnvelopeUri: string;
  readonly sourceEnvelopeSha256: string;
  readonly sourceEnvelopeGeneration: bigint;
  readonly claimId: string;
  readonly claimFencingToken: bigint;
  readonly claimExpiresAt: Date;
  readonly requesterSubjectSha256: string;
  readonly approverSubjectSha256: string;
  readonly approvalEventId: string;
  readonly approvalEventRevision: bigint;
  readonly approvalEvidenceSha256: string;
  readonly approvalPolicyRevisionSha256: string;
  readonly requiredCapability: typeof CAPABILITY;
  readonly expiresAt: Date;
}

export interface CancellationEvidence {
  readonly actorSubjectSha256: string;
  readonly evidenceSha256: string;
  readonly eventId: string;
  readonly eventRevision: bigint;
  readonly requiredCapability: typeof CAPABILITY;
  readonly verified: true;
}

export interface ControlledApplyReservation {
  readonly id: string;
  readonly idempotencyKeyHash: string;
  readonly nonce: string;
  readonly pairingSha256: string;
  readonly sourceEnvelopeUri: string;
  readonly sourceEnvelopeSha256: string;
  readonly sourceEnvelopeGeneration: bigint;
  readonly claimId: string;
  readonly claimFencingToken: bigint;
  readonly requesterSubjectSha256: string;
  readonly approverSubjectSha256: string;
  readonly approvalEventId: string;
  readonly approvalEventRevision: bigint;
  readonly approvalEvidenceSha256: string;
  readonly approvalPolicyRevisionSha256: string;
  readonly reservationReceiptSha256: string;
  readonly completionReceiptSha256: string | null;
  readonly cancellationReceiptSha256: string | null;
  readonly cancellationEvidenceSha256: string | null;
  readonly cancellationActorSubjectSha256: string | null;
  readonly cancellationEventId: string | null;
  readonly cancellationEventRevision: bigint | null;
  readonly state: ControlledApplyReservationState;
  readonly outcome: string | null;
  readonly expiresAt: Date;
  readonly reservedAt: Date;
  readonly completedAt: Date | null;
  readonly cancelledAt: Date | null;
}

export interface CompleteControlledApplyRequest {
  readonly idempotencyKeyHash: string;
  readonly claimId: string;
  readonly claimFencingToken: bigint;
  readonly completionReceiptSha256: string;
  readonly outcome: 'succeeded' | 'failed' | 'unknown';
}

export interface CancelControlledApplyRequest {
  readonly idempotencyKeyHash: string;
  readonly claimId: string;
  readonly claimFencingToken: bigint;
  readonly cancellationReceiptSha256: string;
  readonly evidence: CancellationEvidence;
}

export type ControlledApplyReservationResult =
  | {
      readonly kind: 'reserved';
      readonly reservation: ControlledApplyReservation;
    }
  | {
      readonly kind: 'replay';
      readonly reservation: ControlledApplyReservation;
    };

export function assertVerifiedControlledApplyRequest(
  input: VerifiedControlledApplyRequest,
): void {
  for (const [name, value] of [
    ['idempotencyKeyHash', input.idempotencyKeyHash],
    ['nonce', input.nonce],
    ['pairingSha256', input.pairingSha256],
    ['sourceEnvelopeSha256', input.sourceEnvelopeSha256],
    ['requesterSubjectSha256', input.requesterSubjectSha256],
    ['approverSubjectSha256', input.approverSubjectSha256],
    ['approvalEvidenceSha256', input.approvalEvidenceSha256],
    ['approvalPolicyRevisionSha256', input.approvalPolicyRevisionSha256],
  ] as const) {
    if (!SHA256.test(value))
      throw new ControlledApplyReservationValidationError(
        `${name} must be SHA-256`,
      );
  }
  const expectedIdempotencyHash = createHash('sha256')
    .update(input.idempotencyKey)
    .digest('hex');
  if (input.idempotencyKeyHash !== expectedIdempotencyHash)
    throw new ControlledApplyReservationValidationError(
      'idempotency key hash does not match the key',
    );
  if (!input.idempotencyKey || input.idempotencyKey.length > 512)
    throw new ControlledApplyReservationValidationError(
      'idempotency key is invalid',
    );
  const locator = URI.exec(input.sourceEnvelopeUri);
  if (
    !locator ||
    locator[1] !== input.sourceEnvelopeSha256 ||
    BigInt(locator[2]) !== input.sourceEnvelopeGeneration
  )
    throw new ControlledApplyReservationValidationError(
      'source envelope digest and generation do not match its immutable locator',
    );
  if (!CLAIM_ID.test(input.claimId))
    throw new ControlledApplyReservationValidationError('claimId is invalid');
  if (!CLAIM_ID.test(input.approvalEventId))
    throw new ControlledApplyReservationValidationError(
      'approval event id is invalid',
    );
  if (input.sourceEnvelopeGeneration <= 0n)
    throw new ControlledApplyReservationValidationError(
      'source envelope generation is invalid',
    );
  if (input.claimFencingToken <= 0n)
    throw new ControlledApplyReservationValidationError(
      'claim fencing token is invalid',
    );
  if (input.approvalEventRevision <= 0n)
    throw new ControlledApplyReservationValidationError(
      'approval event revision is invalid',
    );
  if (input.requesterSubjectSha256 === input.approverSubjectSha256)
    throw new ControlledApplyReservationForbiddenError(
      'requester and approver must differ',
    );
  if (input.requiredCapability !== CAPABILITY)
    throw new ControlledApplyReservationForbiddenError(
      'required approval capability is missing',
    );
  if (input.claimExpiresAt <= new Date() || input.expiresAt <= new Date())
    throw new ControlledApplyReservationConflictError(
      'verified request is expired',
    );
  if (input.expiresAt > input.claimExpiresAt)
    throw new ControlledApplyReservationValidationError(
      'reservation exceeds claim expiry',
    );
}

export function reservationReceiptSha256(
  input: Pick<VerifiedControlledApplyRequest, 'idempotencyKeyHash' | 'nonce'>,
): string {
  return createHash('sha256')
    .update(
      `vfbiz-controlled-apply-reservation/v1:${input.idempotencyKeyHash}:${input.nonce}`,
    )
    .digest('hex');
}

/**
 * Validate the receipt persisted with a reservation before replaying or
 * advancing it. The receipt is server-derived and therefore remains an
 * integrity check even when the row is loaded from a previously corrupted
 * store.
 */
export function assertStoredReservationReceipt(
  reservation: Pick<
    ControlledApplyReservation,
    'idempotencyKeyHash' | 'nonce' | 'reservationReceiptSha256'
  >,
): void {
  if (
    reservation.reservationReceiptSha256 !==
    reservationReceiptSha256(reservation)
  )
    throw new ControlledApplyReservationConflictError(
      'stored reservation receipt is invalid',
    );
}

export function assertReceipt(receipt: string, field: string): void {
  if (!SHA256.test(receipt))
    throw new ControlledApplyReservationValidationError(
      `${field} must be SHA-256`,
    );
}

export function assertCancellationEvidence(
  evidence: CancellationEvidence,
): void {
  if (evidence.verified !== true || evidence.requiredCapability !== CAPABILITY)
    throw new ControlledApplyReservationForbiddenError(
      'cancellation evidence is not authenticated',
    );
  if (
    !SHA256.test(evidence.actorSubjectSha256) ||
    !SHA256.test(evidence.evidenceSha256)
  )
    throw new ControlledApplyReservationValidationError(
      'cancellation evidence digest is invalid',
    );
  if (!CLAIM_ID.test(evidence.eventId) || evidence.eventRevision <= 0n)
    throw new ControlledApplyReservationValidationError(
      'cancellation evidence event is invalid',
    );
}

export function assertReservationCurrent(
  reservation: ControlledApplyReservation,
  claimId: string,
  fencingToken: bigint,
  now = new Date(),
): void {
  assertReservationClaim(reservation, claimId, fencingToken);
  if (reservation.state !== 'reserved')
    throw new ControlledApplyReservationConflictError(
      'reservation is terminal',
    );
  if (reservation.expiresAt <= now)
    throw new ControlledApplyReservationConflictError(
      'reservation has expired',
    );
}

export function assertReservationClaim(
  reservation: ControlledApplyReservation,
  claimId: string,
  fencingToken: bigint,
): void {
  if (
    reservation.claimId !== claimId ||
    reservation.claimFencingToken !== fencingToken
  )
    throw new ControlledApplyReservationConflictError(
      'stale claim or fencing token',
    );
}

/**
 * Small state machine used by the persistence adapter to keep terminal
 * receipts immutable. It has no framework or database dependencies.
 */
export class ControlledApplyReservationAggregate {
  private constructor(private current: ControlledApplyReservation) {}

  static fromSnapshot(
    snapshot: ControlledApplyReservation,
  ): ControlledApplyReservationAggregate {
    return new ControlledApplyReservationAggregate(snapshot);
  }

  snapshot(): ControlledApplyReservation {
    return this.current;
  }

  complete(
    input: CompleteControlledApplyRequest,
    now = new Date(),
  ): ControlledApplyReservation {
    assertReservationClaim(
      this.current,
      input.claimId,
      input.claimFencingToken,
    );
    assertStoredReservationReceipt(this.current);
    if (this.current.state === 'completed') {
      if (
        this.current.completionReceiptSha256 ===
          input.completionReceiptSha256 &&
        this.current.outcome === input.outcome
      )
        return this.current;
      throw new ControlledApplyReservationConflictError(
        'completion receipt is immutable',
      );
    }
    assertReservationCurrent(
      this.current,
      input.claimId,
      input.claimFencingToken,
      now,
    );
    this.current = {
      ...this.current,
      state: 'completed',
      completionReceiptSha256: input.completionReceiptSha256,
      outcome: input.outcome,
      completedAt: now,
    };
    return this.current;
  }

  cancel(
    input: CancelControlledApplyRequest,
    now = new Date(),
  ): ControlledApplyReservation {
    assertReservationClaim(
      this.current,
      input.claimId,
      input.claimFencingToken,
    );
    assertStoredReservationReceipt(this.current);
    if (this.current.state === 'cancelled') {
      if (
        this.current.cancellationReceiptSha256 ===
        input.cancellationReceiptSha256
      )
        return this.current;
      throw new ControlledApplyReservationConflictError(
        'cancellation receipt is immutable',
      );
    }
    assertReservationCurrent(
      this.current,
      input.claimId,
      input.claimFencingToken,
      new Date(0),
    );
    this.current = {
      ...this.current,
      state: 'cancelled',
      cancellationReceiptSha256: input.cancellationReceiptSha256,
      cancellationEvidenceSha256: input.evidence.evidenceSha256,
      cancellationActorSubjectSha256: input.evidence.actorSubjectSha256,
      cancellationEventId: input.evidence.eventId,
      cancellationEventRevision: input.evidence.eventRevision,
      outcome: 'cancelled',
      cancelledAt: now,
    };
    return this.current;
  }
}
