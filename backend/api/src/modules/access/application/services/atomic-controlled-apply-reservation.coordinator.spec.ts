import { createHash } from 'node:crypto';
import {
  ControlledApplyReservationAuthorityUnavailableError,
  ControlledApplyReservationConflictError,
} from '../errors/controlled-apply-reservation.errors';
import {
  ControlledApplyAtomicReservationStore,
  type ControlledApplyAtomicReservationTransaction,
} from '../ports/controlled-apply-atomic-reservation';
import { ControlledApplySourceEnvelopeIntegrity } from '../ports/controlled-apply-source-envelope-integrity';
import type { ControlledApplyReservationAuthorityJoin } from '../ports/controlled-apply-authority-join-reader';
import type {
  ControlledApplyReservationResult,
  VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';
import { AtomicControlledApplyReservationCoordinator } from './atomic-controlled-apply-reservation.coordinator';

const digest = (value: string) =>
  createHash('sha256').update(value).digest('hex');
const sourceDigest = digest('atomic-source');
const request: VerifiedControlledApplyRequest = {
  idempotencyKey: 'atomic-reservation-test',
  idempotencyKeyHash: digest('atomic-reservation-test'),
  nonce: digest('atomic-nonce'),
  pairingSha256: digest('pairing'),
  sourceEnvelopeUri: `gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/${sourceDigest}.json#9`,
  sourceEnvelopeSha256: sourceDigest,
  sourceEnvelopeGeneration: 9n,
  claimId: 'claim-atomic-0220',
  claimFencingToken: 2n,
  claimExpiresAt: new Date(Date.now() + 60_000),
  requesterSubjectSha256: digest('requester'),
  approverSubjectSha256: digest('approver'),
  approvalEventId: 'approval-atomic',
  approvalEventRevision: 1n,
  approvalEvidenceSha256: digest('approval-evidence'),
  approvalPolicyRevisionSha256: digest('approval-policy'),
  requiredCapability: 'authorization.approval.approve',
  expiresAt: new Date(Date.now() + 30_000),
};

class FakeSourceIntegrity extends ControlledApplySourceEnvelopeIntegrity {
  shouldFail = false;

  assertExact(): Promise<void> {
    if (this.shouldFail) return Promise.reject(new Error('source down'));
    return Promise.resolve();
  }
}

function approvedJoin(): ControlledApplyReservationAuthorityJoin {
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
    approvalState: 'approved',
    cancelledAt: null,
  };
}

class FakeStore extends ControlledApplyAtomicReservationStore {
  join: ControlledApplyReservationAuthorityJoin | null = approvedJoin();
  transactionCount = 0;
  reserveCount = 0;
  result: ControlledApplyReservationResult = {
    kind: 'reserved',
    reservation: {} as never,
  };

  withSerializable<T>(
    operation: (
      transaction: ControlledApplyAtomicReservationTransaction,
    ) => Promise<T>,
  ): Promise<T> {
    this.transactionCount += 1;
    const transaction: ControlledApplyAtomicReservationTransaction = {
      readReservationAuthorityJoin: () => Promise.resolve(this.join),
      reserve: () => {
        this.reserveCount += 1;
        return Promise.resolve(this.result);
      },
    };
    return operation(transaction);
  }
}

describe('AtomicControlledApplyReservationCoordinator', () => {
  it('rechecks the join inside the transaction before reserving', async () => {
    const store = new FakeStore();
    const sourceIntegrity = new FakeSourceIntegrity();
    const coordinator = new AtomicControlledApplyReservationCoordinator(
      sourceIntegrity,
      store,
    );

    await expect(coordinator.reserve(request)).resolves.toBe(store.result);
    expect(store.transactionCount).toBe(1);
    expect(store.reserveCount).toBe(1);
  });

  it('rejects revocation observed inside the transaction and creates no row', async () => {
    const store = new FakeStore();
    store.join = { ...approvedJoin(), cancelledAt: new Date() };
    const coordinator = new AtomicControlledApplyReservationCoordinator(
      new FakeSourceIntegrity(),
      store,
    );

    await expect(coordinator.reserve(request)).rejects.toThrow(
      ControlledApplyReservationConflictError,
    );
    expect(store.reserveCount).toBe(0);
  });

  it('fails closed when the transaction authority join is unavailable', async () => {
    const store = new FakeStore();
    store.join = null;
    const coordinator = new AtomicControlledApplyReservationCoordinator(
      new FakeSourceIntegrity(),
      store,
    );

    await expect(coordinator.reserve(request)).rejects.toThrow(
      ControlledApplyReservationAuthorityUnavailableError,
    );
    expect(store.reserveCount).toBe(0);
  });

  it('does not open a transaction when exact source verification fails', async () => {
    const store = new FakeStore();
    const sourceIntegrity = new FakeSourceIntegrity();
    sourceIntegrity.shouldFail = true;
    const coordinator = new AtomicControlledApplyReservationCoordinator(
      sourceIntegrity,
      store,
    );

    await expect(coordinator.reserve(request)).rejects.toThrow(
      ControlledApplyReservationAuthorityUnavailableError,
    );
    expect(store.transactionCount).toBe(0);
  });
});
