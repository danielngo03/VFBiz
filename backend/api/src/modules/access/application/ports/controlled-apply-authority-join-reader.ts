import type {
  CancelControlledApplyRequest,
  VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';

/**
 * A row observed by the API from its authoritative workforce/approval store.
 *
 * This is deliberately a read-only boundary. The signed envelope is not an
 * insert command and callers cannot manufacture a join by echoing its fields.
 * A production implementation must read the row inside the same transaction
 * that reserves the nonce and must reject stale, revoked or cancelled claims.
 */
export interface ControlledApplyReservationAuthorityJoin {
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
}

export interface ControlledApplyCancellationAuthorityJoin {
  readonly idempotencyKeyHash: string;
  readonly claimId: string;
  readonly claimFencingToken: bigint;
  readonly actorSubjectSha256: string;
  readonly evidenceSha256: string;
  readonly eventId: string;
  readonly eventRevision: bigint;
  readonly requiredCapability: 'authorization.approval.approve';
  readonly verified: true;
}

/**
 * API-owned read port for independently observed workforce authority.
 * Implementations must never accept an envelope as the source of truth for
 * the rows they return and must fail closed on unavailable or ambiguous data.
 */
export abstract class ControlledApplyAuthorityJoinReader {
  abstract readReservationJoin(
    input: VerifiedControlledApplyRequest,
  ): Promise<ControlledApplyReservationAuthorityJoin | null>;

  abstract readCancellationJoin(
    input: CancelControlledApplyRequest,
  ): Promise<ControlledApplyCancellationAuthorityJoin | null>;
}
