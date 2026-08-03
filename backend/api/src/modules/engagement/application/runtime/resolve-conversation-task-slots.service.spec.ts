import { type ConversationTaskProposal } from '../ports/conversation-task-slot-authority';
import { ResolveConversationTaskSlotsService } from './resolve-conversation-task-slots.service';

const now = new Date('2026-07-25T08:00:00.000Z');
const expiresAt = new Date('2026-07-25T09:00:00.000Z');
const taskId = '423e4567-e89b-42d3-a456-426614174000';
const turnId = '223e4567-e89b-42d3-a456-426614174000';
const accessScope = {
  capabilityHash: 'a'.repeat(64),
  kind: 'public_capability' as const,
  profile: 'public_customer' as const,
};
const release = {
  activationId: '00000000-0000-4000-8000-000000000010',
  graphRevision: 'graph-r1',
  knowledgeRevision: 'knowledge-r1',
  manifestSha256: 'b'.repeat(64),
  policyRevision: 'policy-r1',
};
const candidate = {
  candidateId: '323e4567-e89b-42d3-a456-426614174000',
  confidence: 1,
  expectedTaskVersion: 0,
  kind: 'candidate' as const,
  proposedValue: 'VF 8',
  provenanceDigest: 'c'.repeat(64),
  slot: 'vehicle_model',
  sourceTurnId: turnId,
  taskId,
};
const proposal: ConversationTaskProposal = {
  authorizationContextDigest: 'd'.repeat(64),
  expectedTaskVersion: 0,
  expiresAt,
  intent: 'vehicle_question',
  intentRevision: 'router-r1',
  pendingSlots: ['vehicle_model'],
  provenanceDigest: 'e'.repeat(64),
  release,
  slotCandidates: [candidate],
  sourceTurnId: turnId,
  taskId,
};
const receipt = {
  authority: 'vehicle_catalog' as const,
  authorityDigest: 'f'.repeat(64),
  confirmedAt: now,
  expiresAt,
  kind: 'receipt' as const,
  opaqueReference: `vehicle:ref/v1/${'1'.repeat(64)}`,
  provenanceDigest: '9'.repeat(64),
  slot: 'vehicle_model',
  sourceRevision: 'vehicle-catalog-v1',
  taskId,
};

describe('ResolveConversationTaskSlotsService', () => {
  it('converts an AI candidate into an authority receipt', async () => {
    const { authority, service } = fixture();
    authority.resolve.mockResolvedValue({
      kind: 'resolved',
      receipt,
      slot: candidate.slot,
      taskId,
    });

    const delta = await service.resolve({
      accessScope,
      assistantProfile: 'public_customer',
      confirmedEntities: [],
      currentTask: null,
      proposal,
    });

    expect(delta.collectedSlots).toEqual({ vehicle_model: receipt });
    expect(delta.pendingSlots).toEqual([]);
    expect(delta.nextState).toBe('active');
    expect(JSON.stringify(delta)).not.toContain(candidate.proposedValue);
  });

  it('validates a receipt against time observed after authority resolution', async () => {
    const confirmedAt = new Date(now.getTime() + 5);
    const authority = {
      resolve: jest.fn().mockResolvedValue({
        kind: 'resolved',
        receipt: { ...receipt, confirmedAt },
        slot: candidate.slot,
        taskId,
      }),
    };
    const observedTimes: readonly Date[] = [
      now,
      new Date(confirmedAt.getTime() + 1),
    ];
    let observedTimeIndex = 0;
    const service = new ResolveConversationTaskSlotsService(authority, {
      now: () => observedTimes[observedTimeIndex++] ?? confirmedAt,
    });

    await expect(
      service.resolve({
        accessScope,
        assistantProfile: 'public_customer',
        confirmedEntities: [],
        currentTask: null,
        proposal,
      }),
    ).resolves.toMatchObject({
      collectedSlots: {
        vehicle_model: { confirmedAt },
      },
    });
  });

  it('keeps an unresolved slot pending without persisting the proposed value', async () => {
    const { authority, service } = fixture();
    authority.resolve.mockResolvedValue({
      kind: 'unresolved',
      reason: 'not_found',
    });

    const delta = await service.resolve({
      accessScope,
      assistantProfile: 'public_customer',
      confirmedEntities: [],
      currentTask: null,
      proposal,
    });

    expect(delta.collectedSlots).toEqual({});
    expect(delta.pendingSlots).toEqual(['vehicle_model']);
    expect(delta.nextState).toBe('awaiting_clarification');
    expect(JSON.stringify(delta)).not.toContain(candidate.proposedValue);
  });

  it('fails closed when the authority rejects or cannot verify a candidate', async () => {
    const { authority, service } = fixture();
    authority.resolve.mockResolvedValue({
      kind: 'rejected',
      reason: 'unauthorized',
    });

    await expect(
      service.resolve({
        accessScope,
        assistantProfile: 'public_customer',
        confirmedEntities: [],
        currentTask: null,
        proposal,
      }),
    ).rejects.toMatchObject({ code: 'AUTHORITY_FAILED' });
  });

  it('rejects a receipt bound to another task or slot', async () => {
    const { authority, service } = fixture();
    authority.resolve.mockResolvedValue({
      kind: 'resolved',
      receipt,
      slot: 'vehicle_variant',
      taskId,
    });

    await expect(
      service.resolve({
        accessScope,
        assistantProfile: 'public_customer',
        confirmedEntities: [],
        currentTask: null,
        proposal,
      }),
    ).rejects.toMatchObject({ code: 'RECEIPT_BINDING_MISMATCH' });
  });

  it('rejects stale task versions before calling the business authority', async () => {
    const { authority, service } = fixture();
    await expect(
      service.resolve({
        accessScope,
        assistantProfile: 'public_customer',
        confirmedEntities: [],
        currentTask: {
          authorizationContextDigest: proposal.authorizationContextDigest,
          closedAt: null,
          collectedSlots: {},
          expiresAt,
          intent: proposal.intent,
          intentRevision: proposal.intentRevision,
          lastFencingToken: 1,
          pendingSlots: proposal.pendingSlots,
          provenanceDigest: proposal.provenanceDigest,
          release,
          sourceTurnId: turnId,
          state: 'awaiting_clarification',
          taskId,
          taskVersion: 1,
        },
        proposal,
      }),
    ).rejects.toMatchObject({ code: 'CANDIDATE_BINDING_MISMATCH' });
    expect(authority.resolve).not.toHaveBeenCalled();
  });
});

function fixture() {
  const authority = {
    resolve: jest.fn(),
  };
  return {
    authority,
    service: new ResolveConversationTaskSlotsService(authority, {
      now: () => now,
    }),
  };
}
