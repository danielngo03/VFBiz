import { createHash } from 'node:crypto';
import {
  ConversationBudgetExceededError,
  ConversationBudgetValidationError,
  ConversationInputValidationError,
  ConversationInvalidTransitionError,
  ConversationRuntimeAggregate,
  ConversationStaleFencingTokenError,
  ConversationVersionConflictError,
  MAX_CONVERSATION_INPUT_CHARACTERS,
  assertConfirmedConversationContextEntity,
  createConversationRuntimeSnapshot,
  decodePublicEventCursor,
  type CustomerSafeTurnOutcome,
} from './conversation-runtime';

const now = new Date('2026-07-23T09:00:00.000Z');
const publicScope = {
  capabilityHash: 'a'.repeat(64),
  kind: 'public_capability' as const,
  profile: 'public_customer' as const,
};
const fingerprint = (value: string): string =>
  createHash('sha256').update(value).digest('hex');

const restore = () =>
  ConversationRuntimeAggregate.restore(
    createConversationRuntimeSnapshot({
      accessScope: publicScope,
      budget: {
        remainingCostMicros: 2_000_000,
        remainingModelTokens: 20_000,
      },
      id: 'conversation-1',
    }),
  );

const accept = (
  aggregate: ConversationRuntimeAggregate,
  overrides: Partial<Parameters<typeof aggregate.acceptMessage>[0]> = {},
) =>
  aggregate.acceptMessage({
    budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
    clientMessageId: 'client-message-1',
    content: 'Tư vấn cho tôi về VF 8',
    eventId: 'event-1',
    expectedVersion: 0,
    now,
    requestFingerprint: fingerprint('message-1'),
    turnId: 'turn-1',
    ...overrides,
  });

describe('ConversationRuntimeAggregate', () => {
  it('assigns monotonic message and public-event sequences while reserving budget', () => {
    const aggregate = restore();

    const first = accept(aggregate);
    const second = accept(aggregate, {
      clientMessageId: 'client-message-2',
      eventId: 'event-2',
      expectedVersion: 1,
      requestFingerprint: fingerprint('message-2'),
      turnId: 'turn-2',
    });

    expect(first.result).toMatchObject({
      conversationVersion: 1,
      eventCursor: 'event-v1:1',
      receivedSequence: 1,
    });
    expect(second.result).toMatchObject({
      conversationVersion: 2,
      eventCursor: 'event-v1:2',
      receivedSequence: 2,
    });
    expect(second.state).toMatchObject({
      budget: {
        remainingCostMicros: 1_800_000,
        remainingModelTokens: 18_000,
      },
      lastPublicEventSequence: 2,
      lastReceivedSequence: 2,
      version: 2,
    });
    expect(decodePublicEventCursor(second.result.eventCursor)).toBe(2);
  });

  it('rejects stale expected versions before changing state', () => {
    const aggregate = restore();
    accept(aggregate);

    expect(() =>
      accept(aggregate, {
        clientMessageId: 'client-message-2',
        eventId: 'event-2',
        expectedVersion: 0,
        requestFingerprint: fingerprint('message-2'),
        turnId: 'turn-2',
      }),
    ).toThrow(ConversationVersionConflictError);
    expect(aggregate.snapshot()).toMatchObject({
      lastReceivedSequence: 1,
      version: 1,
    });
  });

  it('fails closed for oversized input and invalid or unavailable reservations', () => {
    expect(() =>
      accept(restore(), {
        content: 'x'.repeat(MAX_CONVERSATION_INPUT_CHARACTERS + 1),
      }),
    ).toThrow(ConversationInputValidationError);
    expect(() =>
      accept(restore(), {
        budget: { maxCostMicros: 100_000, maxModelTokens: 0 },
      }),
    ).toThrow(ConversationBudgetValidationError);
    expect(() =>
      accept(restore(), {
        budget: { maxCostMicros: 3_000_000, maxModelTokens: 1_000 },
      }),
    ).toThrow(ConversationBudgetExceededError);
  });

  it('rejects stale fencing and a second concurrent turn claim', () => {
    const aggregate = restore();
    accept(aggregate);
    accept(aggregate, {
      clientMessageId: 'client-message-2',
      eventId: 'event-2',
      expectedVersion: 1,
      requestFingerprint: fingerprint('message-2'),
      turnId: 'turn-2',
    });
    aggregate.claimTurn({
      eventId: 'event-3',
      expectedVersion: 2,
      fencingToken: 10,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });

    expect(() =>
      aggregate.completeTurn({
        eventId: 'event-4',
        expectedVersion: 3,
        fencingToken: 9,
        now,
        outcome: {
          citations: [],
          kind: 'answer',
          message: 'Câu trả lời',
        },
        turnId: 'turn-1',
        usage: { costMicros: 10_000, modelTokens: 100 },
      }),
    ).toThrow(ConversationStaleFencingTokenError);
    expect(() =>
      aggregate.claimTurn({
        eventId: 'event-4',
        expectedVersion: 3,
        fencingToken: 11,
        leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
        now,
        turnId: 'turn-2',
        workerId: 'worker-2',
      }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('claims accepted turns in received sequence order', () => {
    const aggregate = restore();
    accept(aggregate);
    accept(aggregate, {
      clientMessageId: 'client-message-2',
      eventId: 'event-2',
      expectedVersion: 1,
      requestFingerprint: fingerprint('message-2'),
      turnId: 'turn-2',
    });

    expect(() =>
      aggregate.claimTurn({
        eventId: 'event-3',
        expectedVersion: 2,
        fencingToken: 1,
        leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
        now,
        turnId: 'turn-2',
        workerId: 'worker-1',
      }),
    ).toThrow(ConversationInvalidTransitionError);
    expect(
      aggregate.claimTurn({
        eventId: 'event-3',
        expectedVersion: 2,
        fencingToken: 1,
        leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
        now,
        turnId: 'turn-1',
        workerId: 'worker-1',
      }).result.turnId,
    ).toBe('turn-1');
  });

  it('allows an expired claim to be fenced by a newer worker', () => {
    const aggregate = restore();
    accept(aggregate);
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 10,
      leaseExpiresAt: new Date('2026-07-23T09:01:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });
    aggregate.claimTurn({
      eventId: 'event-3',
      expectedVersion: 2,
      fencingToken: 11,
      leaseExpiresAt: new Date('2026-07-23T09:06:00.000Z'),
      now: new Date('2026-07-23T09:02:00.000Z'),
      turnId: 'turn-1',
      workerId: 'worker-2',
    });

    expect(() =>
      aggregate.completeTurn({
        eventId: 'event-4',
        expectedVersion: 3,
        fencingToken: 10,
        now: new Date('2026-07-23T09:02:30.000Z'),
        outcome: {
          citations: [],
          kind: 'answer',
          message: 'Late output',
        },
        turnId: 'turn-1',
        usage: { costMicros: 10_000, modelTokens: 100 },
      }),
    ).toThrow(ConversationStaleFencingTokenError);
    expect(
      aggregate.completeTurn({
        eventId: 'event-4',
        expectedVersion: 3,
        fencingToken: 11,
        now: new Date('2026-07-23T09:02:30.000Z'),
        outcome: {
          citations: [],
          kind: 'answer',
          message: 'Current output',
        },
        turnId: 'turn-1',
        usage: { costMicros: 10_000, modelTokens: 100 },
      }).result.outcome,
    ).toBe('answered');
  });

  it('rejects cancellation from an expired claimed lease', () => {
    const aggregate = restore();
    accept(aggregate);
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 10,
      leaseExpiresAt: new Date('2026-07-23T09:01:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });

    expect(() =>
      aggregate.cancelTurn({
        authority: 'worker',
        eventId: 'event-3',
        expectedVersion: 2,
        fencingToken: 10,
        now: new Date('2026-07-23T09:02:00.000Z'),
        reason: 'timeout',
        turnId: 'turn-1',
        usage: { costMicros: 0, modelTokens: 0 },
      }),
    ).toThrow(ConversationStaleFencingTokenError);
  });

  it('validates finite dates and copies caller-owned Date objects', () => {
    expect(() => accept(restore(), { now: new Date(Number.NaN) })).toThrow(
      ConversationInputValidationError,
    );

    const aggregate = restore();
    const acceptedAt = new Date(now);
    const accepted = accept(aggregate, { now: acceptedAt });
    acceptedAt.setUTCFullYear(2030);
    expect(accepted.events[0].occurredAt.toISOString()).toBe(
      '2026-07-23T09:00:00.000Z',
    );

    const leaseExpiresAt = new Date('2026-07-23T09:05:00.000Z');
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 1,
      leaseExpiresAt,
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });
    leaseExpiresAt.setUTCFullYear(2030);
    expect(
      aggregate.snapshot().turns[0]?.claim?.leaseExpiresAt.toISOString(),
    ).toBe('2026-07-23T09:05:00.000Z');
  });

  it('rejects unsafe or malformed citations before publishing an answer', () => {
    const aggregate = restore();
    accept(aggregate);
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });

    expect(() =>
      aggregate.completeTurn({
        eventId: 'event-3',
        expectedVersion: 2,
        fencingToken: 1,
        now,
        outcome: {
          citations: [
            {
              retrievedAt: now,
              revision: 'revision-1',
              sourceId: 'source-1',
              title: 'Nguồn',
              uri: 'javascript:alert(1)',
            },
          ],
          kind: 'answer',
          message: 'Câu trả lời',
        },
        turnId: 'turn-1',
        usage: { costMicros: 10_000, modelTokens: 100 },
      }),
    ).toThrow(ConversationInputValidationError);
    expect(() =>
      aggregate.completeTurn({
        eventId: 'event-3',
        expectedVersion: 2,
        fencingToken: 1,
        now,
        outcome: {
          citations: [
            {
              retrievedAt: new Date(Number.NaN),
              revision: 'revision-1',
              sourceId: 'source-1',
              title: 'Nguồn',
              uri: 'https://example.test/source',
            },
          ],
          kind: 'answer',
          message: 'Câu trả lời',
        },
        turnId: 'turn-1',
        usage: { costMicros: 10_000, modelTokens: 100 },
      }),
    ).toThrow(ConversationInputValidationError);
    for (const citation of [
      {
        retrievedAt: now,
        revision: 'revision-1',
        sourceId: '',
        title: 'Nguồn',
        uri: 'https://example.test/source',
      },
      {
        retrievedAt: now,
        revision: '',
        sourceId: 'source-1',
        title: 'Nguồn',
        uri: 'https://example.test/source',
      },
      {
        retrievedAt: now,
        revision: 'revision-1',
        sourceId: 'source-1',
        title: '   ',
        uri: 'https://example.test/source',
      },
    ]) {
      expect(() =>
        aggregate.completeTurn({
          eventId: 'event-3',
          expectedVersion: 2,
          fencingToken: 1,
          now,
          outcome: {
            citations: [citation],
            kind: 'answer',
            message: 'Câu trả lời',
          },
          turnId: 'turn-1',
          usage: { costMicros: 10_000, modelTokens: 100 },
        }),
      ).toThrow();
    }
  });

  it('creates only customer-safe output even when an upstream object has private fields', () => {
    const aggregate = restore();
    accept(aggregate);
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });
    const upstreamOutput: CustomerSafeTurnOutcome & {
      hiddenReasoning: string;
      rawProviderPayload: unknown;
    } = {
      citations: [
        {
          retrievedAt: now,
          revision: 'knowledge-1',
          sourceId: 'source-1',
          title: 'Thông tin xe',
          uri: 'https://example.test/source-1',
        },
      ],
      hiddenReasoning: 'must never be serialized',
      kind: 'answer',
      message: 'VF 8 là một mẫu SUV điện.',
      rawProviderPayload: { token: 'provider-secret' },
    };

    const completed = aggregate.completeTurn({
      eventId: 'event-3',
      expectedVersion: 2,
      fencingToken: 1,
      now,
      outcome: upstreamOutput,
      turnId: 'turn-1',
      usage: { costMicros: 20_000, modelTokens: 250 },
    });
    const serialized = JSON.stringify(completed.events[0]);

    expect(completed.result.outcome).toBe('answered');
    expect(serialized).not.toContain('hiddenReasoning');
    expect(serialized).not.toContain('rawProviderPayload');
    expect(serialized).not.toContain('provider-secret');
  });

  it('represents cancellation and releases only unused reserved budget', () => {
    const aggregate = restore();
    accept(aggregate);
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 7,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });

    const cancelled = aggregate.cancelTurn({
      authority: 'worker',
      eventId: 'event-3',
      expectedVersion: 2,
      fencingToken: 7,
      now,
      reason: 'timeout',
      turnId: 'turn-1',
      usage: { costMicros: 20_000, modelTokens: 100 },
    });

    expect(cancelled.events[0]).toMatchObject({
      payload: { reason: 'timeout', turnId: 'turn-1' },
      type: 'turn.cancelled',
    });
    expect(cancelled.state).toMatchObject({
      budget: {
        remainingCostMicros: 1_980_000,
        remainingModelTokens: 19_900,
      },
    });
    expect(() =>
      aggregate.cancelTurn({
        authority: 'worker',
        eventId: 'event-4',
        expectedVersion: 3,
        fencingToken: 7,
        now,
        reason: 'timeout',
        turnId: 'turn-1',
        usage: { costMicros: 0, modelTokens: 0 },
      }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('persists a bounded release receipt and rejects it after expiry', () => {
    const aggregate = restore();
    accept(aggregate);
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 7,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });
    const receipt = {
      activationEnvelopeSha256: 'b'.repeat(64),
      activationId: '00000000-0000-4000-8000-000000000010',
      candidateSha256: 'a'.repeat(64),
      conversationVersion: 2,
      expiresAt: new Date('2026-07-23T09:00:15.000Z'),
      fencingToken: 7,
      issuedAt: now,
      leaseId: '00000000-0000-4000-8000-000000000001',
      pointerRevision: 3,
      requestId: 'request-1',
      sessionId: 'conversation-1',
      turnId: 'turn-1',
    };

    const completed = aggregate.completeTurn({
      assistantReleaseReceipt: receipt,
      assistantReleaseRevision: '00000000-0000-4000-8000-000000000010',
      eventId: 'event-3',
      expectedVersion: 2,
      fencingToken: 7,
      now,
      outcome: { kind: 'refusal', message: 'Không đủ bằng chứng.' },
      turnId: 'turn-1',
      usage: { costMicros: 100, modelTokens: 10 },
    });

    expect(completed.state.turns[0]?.assistantReleaseReceipt).toEqual(receipt);

    const stale = restore();
    accept(stale);
    stale.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 7,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });
    expect(() =>
      stale.completeTurn({
        assistantReleaseReceipt: receipt,
        assistantReleaseRevision: '00000000-0000-4000-8000-000000000010',
        eventId: 'event-3',
        expectedVersion: 2,
        fencingToken: 7,
        now: new Date('2026-07-23T09:00:16.000Z'),
        outcome: { kind: 'refusal', message: 'Không đủ bằng chứng.' },
        turnId: 'turn-1',
        usage: { costMicros: 100, modelTokens: 10 },
      }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('makes handoff a durable terminal state rather than a transport state', () => {
    const aggregate = restore();
    accept(aggregate);
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 4,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });

    const handoff = aggregate.completeTurn({
      eventId: 'event-3',
      expectedVersion: 2,
      fencingToken: 4,
      now,
      outcome: {
        customerMessage: 'Em đang chuyển anh/chị tới nhân viên hỗ trợ.',
        handoffId: 'handoff-1',
        kind: 'handoff',
        reason: 'customer_requested',
      },
      turnId: 'turn-1',
      usage: { costMicros: 5_000, modelTokens: 50 },
    });

    expect(handoff.state.status).toBe('handoff');
    expect(handoff.events[0]).toMatchObject({
      payload: {
        handoffId: 'handoff-1',
        status: 'queued',
      },
      type: 'handoff.requested',
    });
    expect(() =>
      accept(aggregate, {
        clientMessageId: 'client-message-2',
        eventId: 'event-4',
        expectedVersion: 3,
        requestFingerprint: fingerprint('message-2'),
        turnId: 'turn-2',
      }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('closes an open session, publishes a durable event and blocks further messages', () => {
    const aggregate = restore();

    const closed = aggregate.closeSession({
      eventId: 'event-1',
      expectedVersion: 0,
      now,
    });

    expect(closed.state.status).toBe('closed');
    expect(closed.result.conversationVersion).toBe(1);
    expect(closed.events[0]).toMatchObject({
      payload: {},
      type: 'session.closed',
    });
    expect(decodePublicEventCursor(closed.result.eventCursor)).toBe(1);
    expect(() =>
      accept(aggregate, { eventId: 'event-2', expectedVersion: 1 }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('closes a session already in handoff status', () => {
    const aggregate = restore();
    accept(aggregate);
    aggregate.claimTurn({
      eventId: 'event-2',
      expectedVersion: 1,
      fencingToken: 4,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      now,
      turnId: 'turn-1',
      workerId: 'worker-1',
    });
    aggregate.completeTurn({
      eventId: 'event-3',
      expectedVersion: 2,
      fencingToken: 4,
      now,
      outcome: {
        customerMessage: 'Em đang chuyển anh/chị tới nhân viên hỗ trợ.',
        handoffId: 'handoff-1',
        kind: 'handoff',
        reason: 'customer_requested',
      },
      turnId: 'turn-1',
      usage: { costMicros: 5_000, modelTokens: 50 },
    });

    const closed = aggregate.closeSession({
      eventId: 'event-4',
      expectedVersion: 3,
      now,
    });

    expect(closed.state.status).toBe('closed');
  });

  it('rejects closing an already-closed session', () => {
    const aggregate = restore();
    aggregate.closeSession({ eventId: 'event-1', expectedVersion: 0, now });

    expect(() =>
      aggregate.closeSession({ eventId: 'event-2', expectedVersion: 1, now }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('rejects closing with a stale expected version before changing state', () => {
    const aggregate = restore();
    accept(aggregate);

    expect(() =>
      aggregate.closeSession({ eventId: 'event-2', expectedVersion: 0, now }),
    ).toThrow(ConversationVersionConflictError);
    expect(aggregate.snapshot().status).toBe('open');
  });

  it('requests a customer-initiated handoff with no owning turn', () => {
    const aggregate = restore();

    const handoff = aggregate.requestHandoff({
      customerMessage: 'Tôi muốn nói chuyện với nhân viên hỗ trợ.',
      eventId: 'event-1',
      expectedVersion: 0,
      handoffId: 'handoff-1',
      now,
    });

    expect(handoff.state.status).toBe('handoff');
    expect(handoff.result.handoffId).toBe('handoff-1');
    expect(handoff.events[0]).toMatchObject({
      payload: {
        customerMessage: 'Tôi muốn nói chuyện với nhân viên hỗ trợ.',
        handoffId: 'handoff-1',
        reason: 'customer_requested',
        status: 'queued',
      },
      type: 'handoff.requested',
    });
    expect(handoff.events[0].payload).not.toHaveProperty('turnId');
    expect(() =>
      accept(aggregate, { eventId: 'event-2', expectedVersion: 1 }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('rejects a second handoff request once already in handoff status', () => {
    const aggregate = restore();
    aggregate.requestHandoff({
      customerMessage: 'Cần hỗ trợ gấp.',
      eventId: 'event-1',
      expectedVersion: 0,
      handoffId: 'handoff-1',
      now,
    });

    expect(() =>
      aggregate.requestHandoff({
        customerMessage: 'Cần hỗ trợ gấp lần nữa.',
        eventId: 'event-2',
        expectedVersion: 1,
        handoffId: 'handoff-2',
        now,
      }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('rejects requesting handoff on an already-closed session', () => {
    const aggregate = restore();
    aggregate.closeSession({ eventId: 'event-1', expectedVersion: 0, now });

    expect(() =>
      aggregate.requestHandoff({
        customerMessage: 'Cần hỗ trợ.',
        eventId: 'event-2',
        expectedVersion: 1,
        handoffId: 'handoff-1',
        now,
      }),
    ).toThrow(ConversationInvalidTransitionError);
  });

  it('rejects requesting handoff with a stale expected version before changing state', () => {
    const aggregate = restore();
    accept(aggregate);

    expect(() =>
      aggregate.requestHandoff({
        customerMessage: 'Cần hỗ trợ.',
        eventId: 'event-2',
        expectedVersion: 0,
        handoffId: 'handoff-1',
        now,
      }),
    ).toThrow(ConversationVersionConflictError);
    expect(aggregate.snapshot().status).toBe('open');
  });
});

describe('confirmed conversation context', () => {
  const confirmedAt = new Date('2026-07-27T10:00:00.000Z');
  const base = {
    authority: 'vehicle-catalog',
    classification: 'non_sensitive' as const,
    confirmedAt,
    expiresAt: new Date('2026-07-28T10:00:00.000Z'),
    kind: 'vehicle_model' as const,
    opaqueReference: 'vf-8',
    provenanceDigest: 'a'.repeat(64),
    sourceRevision: 'b'.repeat(64),
  };

  it('accepts only authority-confirmed opaque references', () => {
    expect(() => assertConfirmedConversationContextEntity(base)).not.toThrow();
  });

  it.each(['LHDXXXXXXXXXXXXXXX', 'customer@example.com', '+84901234567'])(
    'rejects raw sensitive reference %s',
    (opaqueReference) => {
      expect(() =>
        assertConfirmedConversationContextEntity({ ...base, opaqueReference }),
      ).toThrow('Invalid confirmed conversation context reference.');
    },
  );

  it('rejects expired confirmation windows and untrusted source revisions', () => {
    expect(() =>
      assertConfirmedConversationContextEntity({
        ...base,
        expiresAt: confirmedAt,
      }),
    ).toThrow('Invalid confirmed conversation context entity.');
    expect(() =>
      assertConfirmedConversationContextEntity({
        ...base,
        sourceRevision: 'catalog-r1',
      }),
    ).toThrow('Invalid confirmed conversation context entity.');
  });
});
