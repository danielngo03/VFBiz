import { CatalogConversationTaskSlotAuthority } from './catalog-conversation-task-slot-authority';

const now = new Date('2026-07-29T08:00:00.000Z');
const candidate = {
  candidateId: '323e4567-e89b-42d3-a456-426614174000',
  confidence: 1,
  expectedTaskVersion: 1,
  kind: 'candidate' as const,
  proposedValue: 'VF 8',
  provenanceDigest: 'c'.repeat(64),
  slot: 'vehicle_model',
  sourceTurnId: '223e4567-e89b-42d3-a456-426614174000',
  taskId: '423e4567-e89b-42d3-a456-426614174000',
};
const release = {
  activationId: '00000000-0000-4000-8000-000000000010',
  graphRevision: 'graph-r1',
  knowledgeRevision: 'knowledge-r1',
  manifestSha256: 'b'.repeat(64),
  policyRevision: 'policy-r1',
};
const market = {
  authority: 'market-catalog',
  classification: 'non_sensitive' as const,
  confirmedAt: new Date('2026-07-29T07:55:00.000Z'),
  expiresAt: new Date('2026-07-29T08:30:00.000Z'),
  kind: 'market' as const,
  opaqueReference: 'VN',
  provenanceDigest: 'd'.repeat(64),
  sourceRevision: 'e'.repeat(64),
};

describe('CatalogConversationTaskSlotAuthority', () => {
  beforeEach(() => {
    jest.useFakeTimers().setSystemTime(now);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('issues a task/slot-bound opaque receipt from the active catalog', async () => {
    const catalog = {
      resolveModel: jest.fn().mockResolvedValue({
        kind: 'resolved',
        value: {
          modelId: 'vehicle-model-vf8',
          modelReference: 'vf-8',
          releaseRevision: 'catalog-release-v1',
          sourceRevision: 'source-r1',
        },
      }),
    };
    const authority = new CatalogConversationTaskSlotAuthority(catalog);

    const result = await authority.resolve({
      candidate,
      confirmedEntities: [market],
      release,
    });

    expect(result).toMatchObject({
      kind: 'resolved',
      receipt: {
        authority: 'vehicle_catalog',
        kind: 'receipt',
        slot: candidate.slot,
        sourceRevision: 'source-r1',
        taskId: candidate.taskId,
      },
      slot: candidate.slot,
      taskId: candidate.taskId,
    });
    if (result.kind !== 'resolved') throw new Error('Expected a receipt');
    expect(result.receipt.opaqueReference).toMatch(
      /^vehicle:ref\/v1\/[a-f0-9]{64}$/,
    );
    expect(JSON.stringify(result)).not.toContain(candidate.proposedValue);
  });

  it('does not query the catalog without a fresh authoritative market', async () => {
    const catalog = { resolveModel: jest.fn() };
    const authority = new CatalogConversationTaskSlotAuthority(catalog);

    await expect(
      authority.resolve({
        candidate,
        confirmedEntities: [],
        release,
      }),
    ).resolves.toEqual({ kind: 'unresolved', reason: 'not_found' });
    expect(catalog.resolveModel).not.toHaveBeenCalled();
  });

  it('rejects a market context issued by an unapproved authority', async () => {
    const catalog = { resolveModel: jest.fn() };
    const authority = new CatalogConversationTaskSlotAuthority(catalog);

    await expect(
      authority.resolve({
        candidate,
        confirmedEntities: [{ ...market, authority: 'model-proposal' }],
        release,
      }),
    ).resolves.toEqual({ kind: 'unresolved', reason: 'not_found' });
    expect(catalog.resolveModel).not.toHaveBeenCalled();
  });

  it('binds receipt evidence to the authoritative market context', async () => {
    const catalog = {
      resolveModel: jest.fn().mockResolvedValue({
        kind: 'resolved',
        value: {
          modelId: 'vehicle-model-vf8',
          modelReference: 'vf-8',
          releaseRevision: 'catalog-release-v1',
          sourceRevision: 'source-r1',
        },
      }),
    };
    const authority = new CatalogConversationTaskSlotAuthority(catalog);

    const vn = await authority.resolve({
      candidate,
      confirmedEntities: [market],
      release,
    });
    const us = await authority.resolve({
      candidate,
      confirmedEntities: [
        {
          ...market,
          opaqueReference: 'US',
          provenanceDigest: 'f'.repeat(64),
          sourceRevision: '1'.repeat(64),
        },
      ],
      release,
    });

    if (vn.kind !== 'resolved' || us.kind !== 'resolved') {
      throw new Error('Expected market-bound receipts');
    }
    expect(vn.receipt.authorityDigest).not.toBe(us.receipt.authorityDigest);
    expect(vn.receipt.provenanceDigest).not.toBe(us.receipt.provenanceDigest);
  });

  it('supports only the explicitly released vehicle_model resolver', async () => {
    const catalog = { resolveModel: jest.fn() };
    const authority = new CatalogConversationTaskSlotAuthority(catalog);

    await expect(
      authority.resolve({
        candidate: { ...candidate, slot: 'vehicle_variant' },
        confirmedEntities: [market],
        release,
      }),
    ).resolves.toEqual({ kind: 'unresolved', reason: 'unsupported_slot' });
    expect(catalog.resolveModel).not.toHaveBeenCalled();
  });
});
