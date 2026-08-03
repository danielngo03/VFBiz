import {
  ConversationController,
  toCustomerSseEvent,
} from './conversation.controller';

const SESSION_ID = '018f47a2-4e68-4c2b-8c23-4c6da5903a41';
const TURN_ID = '118f47a2-4e68-4c2b-8c23-4c6da5903a42';
const createdAt = new Date('2026-08-01T10:00:00.000Z');
const expiresAt = new Date('2026-08-01T10:30:00.000Z');
const retentionUntil = new Date('2026-08-02T10:00:00.000Z');
const accessScope = { kind: 'authenticated-subject' };
const request = {
  vfbizConversationAuthorization: { accessScope },
  vfbizPrincipal: { issuer: 'https://issuer.example', subject: 'customer-1' },
};

describe('ConversationController candidate contract parity', () => {
  const create = {
    execute: jest.fn().mockResolvedValue({
      capability: null,
      expiresInSeconds: 1800,
      session: {
        createdAt,
        expiresAt,
        id: SESSION_ID,
        locale: 'vi',
        profile: 'authenticated_customer',
        retentionUntil,
      },
    }),
  };
  const sessions = {
    findSessionSummary: jest.fn().mockResolvedValue({
      createdAt,
      expiresAt,
      id: SESSION_ID,
      locale: 'vi',
      profile: 'authenticated_customer',
      retentionUntil,
    }),
    listMessages: jest.fn().mockResolvedValue([]),
  };
  const runtime = {
    acceptMessage: jest.fn().mockResolvedValue({
      clientMessageId: '218f47a2-4e68-4c2b-8c23-4c6da5903a43',
      conversationVersion: 1,
      eventCursor: 'event-v1:1',
      receivedSequence: 1,
      replayed: false,
      turnId: TURN_ID,
    }),
    cancelTurnByCustomer: jest.fn().mockResolvedValue({
      conversationVersion: 2,
      eventCursor: 'event-v1:2',
    }),
    closeSession: jest.fn().mockResolvedValue({
      conversationVersion: 1,
      eventCursor: 'event-v1:1',
    }),
    getRuntimeStatus: jest
      .fn()
      .mockResolvedValue({ conversationVersion: 0, status: 'open' }),
    requestHandoff: jest.fn().mockResolvedValue({
      conversationVersion: 1,
      eventCursor: 'event-v1:1',
    }),
  };
  const dispatcher = {
    isEnabled: jest.fn().mockReturnValue(true),
    kick: jest.fn(),
  };
  const controller = new ConversationController(
    create as never,
    sessions as never,
    runtime as never,
    {} as never,
    {} as never,
    dispatcher as never,
  );

  beforeEach(() => jest.clearAllMocks());

  it('projects a complete authenticated session with active public status', async () => {
    await expect(
      controller.createSession({ locale: 'vi' }, request as never),
    ).resolves.toMatchObject({
      expiresAt,
      id: SESSION_ID,
      retentionUntil,
      status: 'active',
      version: 0,
    });
    await expect(
      controller.getSession(SESSION_ID, request as never),
    ).resolves.toMatchObject({
      status: 'active',
      version: 0,
    });
  });

  it('wraps message history and preserves the governed client budget', async () => {
    await expect(
      controller.listMessages(SESSION_ID, request as never),
    ).resolves.toEqual({
      items: [],
      nextCursor: null,
    });
    const budget = { maxCostMicros: 50_000, maxModelTokens: 2_048 };
    await expect(
      controller.createMessage(
        SESSION_ID,
        {
          budget,
          clientMessageId: '218f47a2-4e68-4c2b-8c23-4c6da5903a43',
          content: 'Xin chào',
          expectedVersion: 0,
          kind: 'message.enqueue',
        },
        '218f47a2-4e68-4c2b-8c23-4c6da5903a43',
        request as never,
      ),
    ).resolves.toMatchObject({ kind: 'message.accepted', turnId: TURN_ID });
    expect(runtime.acceptMessage).toHaveBeenCalledWith(
      expect.objectContaining({ budget }),
    );
  });

  it('projects cancel, handoff and close into candidate response shapes', async () => {
    await expect(
      controller.cancelTurn(
        SESSION_ID,
        TURN_ID,
        { expectedVersion: 1, kind: 'turn.cancel', reason: 'user_interrupt' },
        request as never,
      ),
    ).resolves.toEqual({
      conversationVersion: 2,
      eventCursor: 'event-v1:2',
      sessionId: SESSION_ID,
      status: 'accepted',
    });
    await expect(
      controller.requestHandoff(
        SESSION_ID,
        {
          expectedVersion: 0,
          kind: 'handoff.request',
          reason: 'customer_requested',
        },
        request as never,
      ),
    ).resolves.toMatchObject({ sessionId: SESSION_ID, status: 'accepted' });
    runtime.getRuntimeStatus.mockResolvedValueOnce({
      conversationVersion: 1,
      status: 'closed',
    });
    await expect(
      controller.closeSession(SESSION_ID, '"conversation-0"', request as never),
    ).resolves.toMatchObject({ id: SESSION_ID, status: 'closed', version: 1 });
    expect(runtime.closeSession).toHaveBeenCalledWith(
      expect.objectContaining({ expectedVersion: 0 }),
    );
  });

  it('maps durable domain payloads into the public SSE envelope', () => {
    expect(
      toCustomerSseEvent(
        {
          cursor: 'event-v1:1',
          eventId: '318f47a2-4e68-4c2b-8c23-4c6da5903a44',
          occurredAt: createdAt,
          payload: {
            clientMessageId: '218f47a2-4e68-4c2b-8c23-4c6da5903a43',
            receivedSequence: 1,
            turnId: TURN_ID,
          },
          schemaVersion: 1,
          sequence: 1,
          sessionId: SESSION_ID,
          type: 'message.accepted',
        },
        '418f47a2-4e68-4c2b-8c23-4c6da5903a45',
      ),
    ).toEqual({
      correlationId: '418f47a2-4e68-4c2b-8c23-4c6da5903a45',
      data: {
        clientMessageId: '218f47a2-4e68-4c2b-8c23-4c6da5903a43',
        receivedSequence: 1,
      },
      eventId: '318f47a2-4e68-4c2b-8c23-4c6da5903a44',
      occurredAt: createdAt.toISOString(),
      schemaVersion: 1,
      sequence: 1,
      sessionId: SESSION_ID,
      turnId: TURN_ID,
      type: 'message.accepted',
    });
  });

  it('preserves governed cancellation and handoff reason vocabularies', () => {
    expect(
      toCustomerSseEvent(
        {
          cursor: 'event-v1:2',
          eventId: '518f47a2-4e68-4c2b-8c23-4c6da5903a46',
          occurredAt: createdAt,
          payload: { reason: 'system_shutdown', turnId: TURN_ID },
          schemaVersion: 1,
          sequence: 2,
          sessionId: SESSION_ID,
          type: 'turn.cancelled',
        },
        '418f47a2-4e68-4c2b-8c23-4c6da5903a45',
      ),
    ).toMatchObject({
      data: { reason: 'system_shutdown' },
      turnId: TURN_ID,
      type: 'turn.cancelled',
    });

    const handoff = toCustomerSseEvent(
      {
        cursor: 'event-v1:3',
        eventId: '618f47a2-4e68-4c2b-8c23-4c6da5903a47',
        occurredAt: createdAt,
        payload: {
          customerMessage: 'Tôi sẽ chuyển yêu cầu này cho chuyên viên.',
          handoffId: '718f47a2-4e68-4c2b-8c23-4c6da5903a48',
          reason: 'safety_risk',
          status: 'queued',
        },
        schemaVersion: 1,
        sequence: 3,
        sessionId: SESSION_ID,
        type: 'handoff.requested',
      },
      '418f47a2-4e68-4c2b-8c23-4c6da5903a45',
    );
    expect(handoff).toMatchObject({
      data: { reason: 'safety_risk' },
      type: 'handoff.requested',
    });
    expect(handoff).not.toHaveProperty('turnId');
  });

  it('serializes citation timestamps into the public wire format', () => {
    expect(
      toCustomerSseEvent(
        {
          cursor: 'event-v1:4',
          eventId: '818f47a2-4e68-4c2b-8c23-4c6da5903a49',
          occurredAt: createdAt,
          payload: {
            citations: [
              {
                retrievedAt: createdAt,
                revision: 'sha256:source-revision',
                sourceId: 'source-1',
                title: 'Tài liệu kiểm thử',
                uri: 'https://example.test/source-1',
              },
            ],
            message: 'Câu trả lời có nguồn.',
            outcome: 'answered',
            turnId: TURN_ID,
          },
          schemaVersion: 1,
          sequence: 4,
          sessionId: SESSION_ID,
          type: 'turn.completed',
        },
        '418f47a2-4e68-4c2b-8c23-4c6da5903a45',
      ),
    ).toMatchObject({
      data: {
        citations: [{ retrievedAt: createdAt.toISOString() }],
        outcome: 'answered',
      },
    });
  });
});
