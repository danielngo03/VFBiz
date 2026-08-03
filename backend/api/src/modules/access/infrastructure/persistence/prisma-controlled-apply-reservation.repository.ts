import { Injectable } from '@nestjs/common';
import { Prisma } from '../../../../generated/prisma/client';
import { PrismaService } from '../../../../platform/database/prisma.service';
import { isRetryableTransactionError } from '../../../../platform/database/retryable-transaction-error';
import {
  ControlledApplyReservationConflictError,
  ControlledApplyReservationNotFoundError,
} from '../../application/errors/controlled-apply-reservation.errors';
import { ControlledApplyReservationRepository } from '../../application/ports/controlled-apply-reservation.repository';
import {
  assertReservationCurrent,
  assertReservationClaim,
  assertCancellationEvidence,
  assertReceipt,
  assertStoredReservationReceipt,
  assertVerifiedControlledApplyRequest,
  reservationReceiptSha256,
  type CancelControlledApplyRequest,
  type CompleteControlledApplyRequest,
  type ControlledApplyReservation,
  type ControlledApplyReservationResult,
  type VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';

const MAX_SERIALIZABLE_ATTEMPTS = 3;
const reservationSelection = {
  id: true,
  idempotencyKeyHash: true,
  nonce: true,
  pairingSha256: true,
  sourceEnvelopeUri: true,
  sourceEnvelopeSha256: true,
  sourceEnvelopeGeneration: true,
  claimId: true,
  claimFencingToken: true,
  requesterSubjectSha256: true,
  approverSubjectSha256: true,
  approvalEventId: true,
  approvalEventRevision: true,
  approvalEvidenceSha256: true,
  approvalPolicyRevisionSha256: true,
  state: true,
  reservationReceiptSha256: true,
  completionReceiptSha256: true,
  cancellationReceiptSha256: true,
  cancellationEvidenceSha256: true,
  cancellationActorSubjectSha256: true,
  cancellationEventId: true,
  cancellationEventRevision: true,
  outcome: true,
  expiresAt: true,
  reservedAt: true,
  completedAt: true,
  cancelledAt: true,
} as const;
type ReservationRow = Prisma.ControlledApplyReservationGetPayload<{
  select: typeof reservationSelection;
}>;

function view(row: ReservationRow): ControlledApplyReservation {
  return {
    ...row,
    state: row.state.toLowerCase() as ControlledApplyReservation['state'],
  };
}
function sameRequest(
  row: ReservationRow,
  input: VerifiedControlledApplyRequest,
): boolean {
  return (
    row.nonce === input.nonce &&
    row.pairingSha256 === input.pairingSha256 &&
    row.sourceEnvelopeSha256 === input.sourceEnvelopeSha256 &&
    row.sourceEnvelopeGeneration === input.sourceEnvelopeGeneration &&
    row.claimId === input.claimId &&
    row.claimFencingToken === input.claimFencingToken &&
    row.requesterSubjectSha256 === input.requesterSubjectSha256 &&
    row.approverSubjectSha256 === input.approverSubjectSha256 &&
    row.approvalEventId === input.approvalEventId &&
    row.approvalEventRevision === input.approvalEventRevision &&
    row.approvalEvidenceSha256 === input.approvalEvidenceSha256 &&
    row.approvalPolicyRevisionSha256 === input.approvalPolicyRevisionSha256 &&
    row.sourceEnvelopeUri === input.sourceEnvelopeUri
  );
}

@Injectable()
export class PrismaControlledApplyReservationRepository implements ControlledApplyReservationRepository {
  constructor(private readonly prisma: PrismaService) {}

  private async serializable<T>(
    operation: (tx: Prisma.TransactionClient) => Promise<T>,
  ): Promise<T> {
    for (let attempt = 1; attempt <= MAX_SERIALIZABLE_ATTEMPTS; attempt += 1) {
      try {
        return await this.prisma.$transaction(operation, {
          isolationLevel: Prisma.TransactionIsolationLevel.Serializable,
        });
      } catch (error) {
        if (
          !isRetryableTransactionError(error) ||
          attempt === MAX_SERIALIZABLE_ATTEMPTS
        )
          throw error;
      }
    }
    throw new Error('controlled-apply transaction exhausted retries');
  }

  async reserve(
    input: VerifiedControlledApplyRequest,
  ): Promise<ControlledApplyReservationResult> {
    assertVerifiedControlledApplyRequest(input);
    for (let attempt = 1; attempt <= MAX_SERIALIZABLE_ATTEMPTS; attempt += 1) {
      try {
        return await this.prisma.$transaction(
          async (tx) => {
            const existing = await tx.controlledApplyReservation.findUnique({
              where: { idempotencyKeyHash: input.idempotencyKeyHash },
              select: reservationSelection,
            });
            if (existing) {
              if (!sameRequest(existing, input))
                throw new ControlledApplyReservationConflictError(
                  'idempotency key is bound to another request',
                );
              assertStoredReservationReceipt(view(existing));
              return { kind: 'replay', reservation: view(existing) } as const;
            }
            const nonceOwner = await tx.controlledApplyReservation.findUnique({
              where: { nonce: input.nonce },
              select: reservationSelection,
            });
            if (nonceOwner)
              throw new ControlledApplyReservationConflictError(
                'nonce is already bound to another reservation',
              );
            const created = await tx.controlledApplyReservation.create({
              data: {
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
                approvalPolicyRevisionSha256:
                  input.approvalPolicyRevisionSha256,
                state: 'RESERVED',
                reservationReceiptSha256: reservationReceiptSha256(input),
                expiresAt: input.expiresAt,
              },
              select: reservationSelection,
            });
            return { kind: 'reserved', reservation: view(created) } as const;
          },
          { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
        );
      } catch (error) {
        if (
          !isRetryableTransactionError(error) ||
          attempt === MAX_SERIALIZABLE_ATTEMPTS
        )
          throw error;
      }
    }
    throw new Error('controlled-apply reservation exhausted retries');
  }

  async complete(
    input: CompleteControlledApplyRequest,
  ): Promise<ControlledApplyReservation> {
    assertReceipt(input.completionReceiptSha256, 'completion receipt');
    return this.serializable(async (tx) => {
      const existing = await tx.controlledApplyReservation.findUnique({
        where: { idempotencyKeyHash: input.idempotencyKeyHash },
        select: reservationSelection,
      });
      if (!existing)
        throw new ControlledApplyReservationNotFoundError(
          'reservation not found',
        );
      const current = view(existing);
      assertStoredReservationReceipt(current);
      assertReservationClaim(current, input.claimId, input.claimFencingToken);
      if (current.state === 'completed') {
        if (
          current.completionReceiptSha256 === input.completionReceiptSha256 &&
          current.outcome === input.outcome
        )
          return current;
        throw new ControlledApplyReservationConflictError(
          'completion receipt is immutable',
        );
      }
      assertReservationCurrent(current, input.claimId, input.claimFencingToken);
      const updated = await tx.controlledApplyReservation.update({
        where: { id: current.id },
        data: {
          state: 'COMPLETED',
          completionReceiptSha256: input.completionReceiptSha256,
          outcome: input.outcome,
          completedAt: new Date(),
        },
        select: reservationSelection,
      });
      return view(updated);
    });
  }

  async cancel(
    input: CancelControlledApplyRequest,
  ): Promise<ControlledApplyReservation> {
    assertReceipt(input.cancellationReceiptSha256, 'cancellation receipt');
    assertCancellationEvidence(input.evidence);
    return this.serializable(async (tx) => {
      const existing = await tx.controlledApplyReservation.findUnique({
        where: { idempotencyKeyHash: input.idempotencyKeyHash },
        select: reservationSelection,
      });
      if (!existing)
        throw new ControlledApplyReservationNotFoundError(
          'reservation not found',
        );
      const current = view(existing);
      assertStoredReservationReceipt(current);
      assertReservationClaim(current, input.claimId, input.claimFencingToken);
      if (current.state === 'cancelled') {
        if (
          current.cancellationReceiptSha256 === input.cancellationReceiptSha256
        )
          return current;
        throw new ControlledApplyReservationConflictError(
          'cancellation receipt is immutable',
        );
      }
      assertReservationCurrent(
        current,
        input.claimId,
        input.claimFencingToken,
        new Date(0),
      );
      const updated = await tx.controlledApplyReservation.update({
        where: { id: current.id },
        data: {
          state: 'CANCELLED',
          cancellationReceiptSha256: input.cancellationReceiptSha256,
          cancellationEvidenceSha256: input.evidence.evidenceSha256,
          cancellationActorSubjectSha256: input.evidence.actorSubjectSha256,
          cancellationEventId: input.evidence.eventId,
          cancellationEventRevision: input.evidence.eventRevision,
          outcome: 'cancelled',
          cancelledAt: new Date(),
        },
        select: reservationSelection,
      });
      return view(updated);
    });
  }
}
