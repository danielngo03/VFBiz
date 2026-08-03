import { createHash } from 'node:crypto';
import {
  ControlledApplyReservationAuthorityUnavailableError,
  ControlledApplyReservationConflictError,
} from '../../application/errors/controlled-apply-reservation.errors';
import {
  ControlledApplyAuthorityJoinReader,
  type ControlledApplyReservationAuthorityJoin,
  type ControlledApplyCancellationAuthorityJoin,
} from '../../application/ports/controlled-apply-authority-join-reader';
import {
  ControlledApplySourceEnvelopeReader,
  type ControlledApplySourceEnvelopeBytes,
} from '../../application/ports/controlled-apply-source-envelope-reader';
import type {
  CancelControlledApplyRequest,
  VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';
import { crc32cBase64 } from './exact-source-envelope-integrity';
import { SourceAwareControlledApplyAuthorityPreflight } from './source-aware-controlled-apply-authority-verifier';

const digest = (value: string) =>
  createHash('sha256').update(value).digest('hex');
const body = new TextEncoder().encode('{"authority":"api-join"}');
const sourceDigest = createHash('sha256').update(body).digest('hex');
const request: VerifiedControlledApplyRequest = {
  idempotencyKey: 'source-aware-authority-test',
  idempotencyKeyHash: digest('source-aware-authority-test'),
  nonce: digest('source-aware-nonce'),
  pairingSha256: digest('pairing'),
  sourceEnvelopeUri: `gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/${sourceDigest}.json#42`,
  sourceEnvelopeSha256: sourceDigest,
  sourceEnvelopeGeneration: 42n,
  claimId: 'claim-source-aware-0220',
  claimFencingToken: 4n,
  claimExpiresAt: new Date(Date.now() + 60_000),
  requesterSubjectSha256: digest('requester'),
  approverSubjectSha256: digest('approver'),
  approvalEventId: 'approval-source-aware',
  approvalEventRevision: 2n,
  approvalEvidenceSha256: digest('approval-evidence'),
  approvalPolicyRevisionSha256: digest('approval-policy'),
  requiredCapability: 'authorization.approval.approve',
  expiresAt: new Date(Date.now() + 30_000),
};

const cancellation: CancelControlledApplyRequest = {
  idempotencyKeyHash: request.idempotencyKeyHash,
  claimId: request.claimId,
  claimFencingToken: request.claimFencingToken,
  cancellationReceiptSha256: digest('cancel-receipt'),
  evidence: {
    actorSubjectSha256: digest('canceller'),
    evidenceSha256: digest('cancel-evidence'),
    eventId: 'cancel-source-aware',
    eventRevision: 3n,
    requiredCapability: 'authorization.approval.approve',
    verified: true,
  },
};

class FakeSourceReader extends ControlledApplySourceEnvelopeReader {
  readExact(): Promise<ControlledApplySourceEnvelopeBytes> {
    return Promise.resolve({
      generation: 42n,
      sizeBytes: BigInt(body.byteLength),
      crc32cBase64: crc32cBase64(body),
      bytes: (async function* () {
        await Promise.resolve();
        yield body;
      })(),
    });
  }
}

class FakeJoinReader extends ControlledApplyAuthorityJoinReader {
  reservation: ControlledApplyReservationAuthorityJoin | null = null;
  cancellation: ControlledApplyCancellationAuthorityJoin | null = null;

  readReservationJoin() {
    return Promise.resolve(this.reservation);
  }

  readCancellationJoin() {
    return Promise.resolve(this.cancellation);
  }
}

function approvedJoin() {
  return {
    claimId: request.claimId,
    claimFencingToken: request.claimFencingToken,
    claimExpiresAt: request.claimExpiresAt,
    requesterSubjectSha256: request.requesterSubjectSha256,
    approverSubjectSha256: request.approverSubjectSha256,
    approvalEventId: request.approvalEventId,
    approvalEventRevision: request.approvalEventRevision,
    approvalEvidenceSha256: request.approvalEvidenceSha256,
    approvalPolicyRevisionSha256: request.approvalPolicyRevisionSha256,
    requiredCapability: request.requiredCapability,
    approvalState: 'approved' as const,
    cancelledAt: null,
  };
}

function cancellationJoin() {
  return {
    idempotencyKeyHash: cancellation.idempotencyKeyHash,
    claimId: cancellation.claimId,
    claimFencingToken: cancellation.claimFencingToken,
    actorSubjectSha256: cancellation.evidence.actorSubjectSha256,
    evidenceSha256: cancellation.evidence.evidenceSha256,
    eventId: cancellation.evidence.eventId,
    eventRevision: cancellation.evidence.eventRevision,
    requiredCapability: cancellation.evidence.requiredCapability,
    verified: true as const,
  };
}

describe('SourceAwareControlledApplyAuthorityPreflight', () => {
  it('requires exact source bytes and a matching API approval join', async () => {
    const joins = new FakeJoinReader();
    joins.reservation = approvedJoin();
    joins.cancellation = cancellationJoin();
    const verifier = new SourceAwareControlledApplyAuthorityPreflight(
      new FakeSourceReader(),
      joins,
    );

    await expect(verifier.assertReservationPreflight(request)).resolves.toBe(
      undefined,
    );
    await expect(
      verifier.assertCancellationPreflight(cancellation),
    ).resolves.toBe(undefined);
  });

  it('fails closed when the API join is missing or cannot be read', async () => {
    const joins = new FakeJoinReader();
    const verifier = new SourceAwareControlledApplyAuthorityPreflight(
      new FakeSourceReader(),
      joins,
    );
    await expect(verifier.assertReservationPreflight(request)).rejects.toThrow(
      ControlledApplyReservationAuthorityUnavailableError,
    );
    joins.readCancellationJoin = () =>
      Promise.reject(new Error('database down'));
    await expect(
      verifier.assertCancellationPreflight(cancellation),
    ).rejects.toThrow(ControlledApplyReservationAuthorityUnavailableError);
  });

  it('rejects a mismatched or cancelled API join as conflict', async () => {
    const joins = new FakeJoinReader();
    joins.reservation = { ...approvedJoin(), cancelledAt: new Date() };
    const verifier = new SourceAwareControlledApplyAuthorityPreflight(
      new FakeSourceReader(),
      joins,
    );
    await expect(verifier.assertReservationPreflight(request)).rejects.toThrow(
      ControlledApplyReservationConflictError,
    );
    joins.cancellation = { ...cancellationJoin(), eventRevision: 99n };
    await expect(
      verifier.assertCancellationPreflight(cancellation),
    ).rejects.toThrow(ControlledApplyReservationConflictError);
  });

  it('fails closed on malformed API join timestamps', async () => {
    const joins = new FakeJoinReader();
    joins.reservation = {
      ...approvedJoin(),
      claimExpiresAt: 'not-a-date' as unknown as Date,
    };
    const verifier = new SourceAwareControlledApplyAuthorityPreflight(
      new FakeSourceReader(),
      joins,
    );
    await expect(verifier.assertReservationPreflight(request)).rejects.toThrow(
      ControlledApplyReservationConflictError,
    );
  });

  it('normalizes unexpected source-reader failures to authority unavailable', async () => {
    const joins = new FakeJoinReader();
    joins.reservation = approvedJoin();
    const sourceReader = new FakeSourceReader();
    sourceReader.readExact = () => Promise.reject(new Error('provider down'));
    const verifier = new SourceAwareControlledApplyAuthorityPreflight(
      sourceReader,
      joins,
    );

    await expect(verifier.assertReservationPreflight(request)).rejects.toThrow(
      ControlledApplyReservationAuthorityUnavailableError,
    );
  });

  it('does not expose a verified request that could cross a later transaction boundary', () => {
    const joins = new FakeJoinReader();
    const verifier = new SourceAwareControlledApplyAuthorityPreflight(
      new FakeSourceReader(),
      joins,
    );

    expect(verifier).not.toHaveProperty('verifyReservation');
    expect(verifier).not.toHaveProperty('verifyCancellation');
  });
});
