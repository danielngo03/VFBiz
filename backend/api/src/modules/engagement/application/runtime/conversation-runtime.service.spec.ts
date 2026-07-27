import {
  ConversationMessageIdempotencyConflictError,
  ConversationRuntimeNotFoundError,
  ConversationRuntimeService,
} from './conversation-runtime.service';
import {
  ConversationRuntimeClock,
  ConversationRuntimeIdGenerator,
  ConversationRuntimeRepository,
  type AcceptedMessageReplay,
  type ConversationRuntimeCommit,
  type ConversationRuntimeCommitResult,
} from './conversation-runtime.repository';
import {
  ConversationVersionConflictError,
  createConversationRuntimeSnapshot,
  sameConversationAccessScope,
  type ConversationAccessScope,
  type ConversationPublicEvent,
  type ConversationRuntimeSnapshot,
} from '../../domain/runtime/conversation-runtime';

class FixedClock extends ConversationRuntimeClock {
  now(): Date {
    return new Date('2026-07-23T09:00:00.000Z');
  }
}

class SequentialIds extends ConversationRuntimeIdGenerator {
  private event = 0;
  private handoff = 0;
  private turn = 0;

  nextId(purpose: 'event' | 'handoff' | 'turn'): string {
    if (purpose === 'event') return `event-${++this.event}`;
    if (purpose === 'handoff') return `handoff-${++this.handoff}`;
    return `turn-${++this.turn}`;
  }
}

class InMemoryConversationRuntimeRepository extends ConversationRuntimeRepository {
  readonly events: ConversationPublicEvent[] = [];
  private readonly replays = new Map<string, AcceptedMessageReplay>();

  constructor(public state: ConversationRuntimeSnapshot) {
    super();
  }

  findDispatchCandidates() {
    return Promise.resolve([]);
  }

  claimCancellationDispatches() {
    return Promise.resolve([]);
  }

  completeCancellationDispatch() {
    return Promise.resolve();
  }

  retryCancellationDispatch() {
    return Promise.resolve();
  }

  recordTurnDispatchFailure() {
    return Promise.resolve(true);
  }

  commit(
    transition: ConversationRuntimeCommit,
  ): Promise<ConversationRuntimeCommitResult> {
    if (
      !sameConversationAccessScope(
        this.state.accessScope,
        transition.accessScope,
      )
    ) {
      return Promise.resolve({
        actualVersion: this.state.version,
        outcome: 'version-conflict',
      });
    }
    const replay = transition.acceptedMessageReplay;
    if (replay !== undefined) {
      const existing = this.replays.get(replay.result.clientMessageId);
      if (existing !== undefined) {
        return Promise.resolve({ outcome: 'message-replay', replay: existing });
      }
    }
    if (this.state.version !== transition.expectedVersion) {
      return Promise.resolve({
        actualVersion: this.state.version,
        outcome: 'version-conflict',
      });
    }
    this.state = transition.nextState;
    this.events.push(...transition.events);
    if (replay !== undefined) {
      this.replays.set(replay.result.clientMessageId, replay);
    }
    return Promise.resolve({ outcome: 'committed' });
  }

  findAcceptedMessage(
    _sessionId: string,
    accessScope: ConversationAccessScope,
    clientMessageId: string,
  ): Promise<AcceptedMessageReplay | null> {
    if (!sameConversationAccessScope(this.state.accessScope, accessScope)) {
      return Promise.resolve(null);
    }
    return Promise.resolve(this.replays.get(clientMessageId) ?? null);
  }

  getSnapshot(
    _sessionId: string,
    accessScope: ConversationAccessScope,
  ): Promise<ConversationRuntimeSnapshot | null> {
    return Promise.resolve(
      sameConversationAccessScope(this.state.accessScope, accessScope)
        ? this.state
        : null,
    );
  }

  getTurnExecutionContext(): Promise<null> {
    return Promise.resolve(null);
  }

  listPublicEvents(
    _sessionId: string,
    accessScope: ConversationAccessScope,
    afterSequence: number | null,
    limit: number,
  ): ReturnType<ConversationRuntimeRepository['listPublicEvents']> {
    if (!sameConversationAccessScope(this.state.accessScope, accessScope)) {
      return Promise.resolve({ outcome: 'not-found' });
    }
    return Promise.resolve({
      events: this.events
        .filter((event) => event.sequence > (afterSequence ?? 0))
        .slice(0, limit),
      outcome: 'events' as const,
    });
  }

  purgeCustomerSubject(): Promise<number> {
    return Promise.resolve(0);
  }

  purgeExpiredSessions(): Promise<number> {
    return Promise.resolve(0);
  }
}

const publicScope: ConversationAccessScope = {
  capabilityHash: 'a'.repeat(64),
  kind: 'public_capability',
  profile: 'public_customer',
};
const wrongPublicScope: ConversationAccessScope = {
  capabilityHash: 'b'.repeat(64),
  kind: 'public_capability',
  profile: 'public_customer',
};
const authenticatedScope: ConversationAccessScope = {
  issuer: 'https://id.example/realms/customer',
  kind: 'authenticated_customer',
  profile: 'authenticated_customer',
  subject: 'customer-1',
};

const createHarness = (accessScope: ConversationAccessScope = publicScope) => {
  const repository = new InMemoryConversationRuntimeRepository(
    createConversationRuntimeSnapshot({
      accessScope,
      budget: {
        remainingCostMicros: 2_000_000,
        remainingModelTokens: 20_000,
      },
      id: 'conversation-1',
    }),
  );
  return {
    repository,
    service: new ConversationRuntimeService(
      repository,
      new FixedClock(),
      new SequentialIds(),
    ),
  };
};

const message = {
  accessScope: publicScope,
  budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
  clientMessageId: 'client-message-1',
  content: 'Tư vấn VF 8',
  expectedVersion: 0,
  sessionId: 'conversation-1',
};

describe('ConversationRuntimeService', () => {
  it('replays the same client message without another state transition', async () => {
    const { repository, service } = createHarness();

    const accepted = await service.acceptMessage(message);
    const replayed = await service.acceptMessage({
      ...message,
      expectedVersion: 999,
    });

    expect(accepted).toMatchObject({ replayed: false, turnId: 'turn-1' });
    expect(replayed).toEqual({ ...accepted, replayed: true });
    expect(repository.state.version).toBe(1);
    expect(repository.events).toHaveLength(1);
  });

  it('rejects reuse of a client message ID for different input', async () => {
    const { service } = createHarness();
    await service.acceptMessage(message);

    await expect(
      service.acceptMessage({
        ...message,
        content: 'Một nội dung khác',
        expectedVersion: 1,
      }),
    ).rejects.toBeInstanceOf(ConversationMessageIdempotencyConflictError);
  });

  it('does not read or replay a public conversation with the wrong capability hash', async () => {
    const { service } = createHarness();
    await service.acceptMessage(message);

    await expect(
      service.acceptMessage({
        ...message,
        accessScope: wrongPublicScope,
        expectedVersion: 1,
      }),
    ).rejects.toBeInstanceOf(ConversationRuntimeNotFoundError);
    await expect(
      service.listPublicEvents({
        accessScope: wrongPublicScope,
        afterCursor: null,
        sessionId: 'conversation-1',
      }),
    ).resolves.toEqual({ events: [], nextCursor: null });
  });

  it('does not read or replay another authenticated subject conversation', async () => {
    const { service } = createHarness(authenticatedScope);
    const authenticatedMessage = {
      ...message,
      accessScope: authenticatedScope,
    };
    await service.acceptMessage(authenticatedMessage);
    const anotherSubject: ConversationAccessScope = {
      ...authenticatedScope,
      subject: 'customer-2',
    };

    await expect(
      service.acceptMessage({
        ...authenticatedMessage,
        accessScope: anotherSubject,
        expectedVersion: 1,
      }),
    ).rejects.toBeInstanceOf(ConversationRuntimeNotFoundError);
    await expect(
      service.listPublicEvents({
        accessScope: anotherSubject,
        afterCursor: null,
        sessionId: 'conversation-1',
      }),
    ).resolves.toEqual({ events: [], nextCursor: null });
  });

  it('maps a commit-time OCC race to a typed version conflict', async () => {
    const { repository, service } = createHarness();
    const originalCommit = repository.commit.bind(repository);
    jest.spyOn(repository, 'commit').mockImplementationOnce((transition) => {
      repository.state = { ...repository.state, version: 1 };
      return originalCommit(transition);
    });

    await expect(service.acceptMessage(message)).rejects.toBeInstanceOf(
      ConversationVersionConflictError,
    );
    expect(repository.events).toHaveLength(0);
  });

  it('pages public events using an opaque monotonic cursor', async () => {
    const { service } = createHarness();
    const accepted = await service.acceptMessage(message);
    await service.claimTurn({
      accessScope: publicScope,
      expectedVersion: accepted.conversationVersion,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      sessionId: 'conversation-1',
      turnId: accepted.turnId,
      workerId: 'worker-1',
    });

    const first = await service.listPublicEvents({
      accessScope: publicScope,
      afterCursor: null,
      limit: 1,
      sessionId: 'conversation-1',
    });
    const second = await service.listPublicEvents({
      accessScope: publicScope,
      afterCursor: first.nextCursor,
      limit: 1,
      sessionId: 'conversation-1',
    });

    expect(first.events.map((event) => event.type)).toEqual([
      'message.accepted',
    ]);
    expect(second.events.map((event) => event.type)).toEqual([
      'turn.processing',
    ]);
    expect(second.nextCursor).toBe('event-v1:2');
  });

  it('returns a typed recovery requirement when durable replay expired', async () => {
    const { repository, service } = createHarness();
    jest.spyOn(repository, 'listPublicEvents').mockResolvedValueOnce({
      earliestAvailableCursor: 'event-v1:51',
      latestAvailableCursor: 'event-v1:100',
      outcome: 'resync-required',
      reason: 'cursor_expired',
      retentionUntil: new Date('2026-07-24T09:00:00.000Z'),
    });

    await expect(
      service.listPublicEvents({
        accessScope: publicScope,
        afterCursor: 'event-v1:1',
        sessionId: 'conversation-1',
      }),
    ).rejects.toMatchObject({
      earliestAvailableCursor: 'event-v1:51',
      latestAvailableCursor: 'event-v1:100',
      reason: 'cursor_expired',
    });
  });

  it('allocates the durable handoff ID inside the API application boundary', async () => {
    const { service } = createHarness();
    const accepted = await service.acceptMessage(message);
    const claimed = await service.claimTurn({
      accessScope: publicScope,
      expectedVersion: accepted.conversationVersion,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-23T09:05:00.000Z'),
      sessionId: 'conversation-1',
      turnId: accepted.turnId,
      workerId: 'worker-1',
    });

    await expect(
      service.completeTurn({
        accessScope: publicScope,
        expectedVersion: claimed.conversationVersion,
        fencingToken: 1,
        outcome: {
          customerMessage: 'Em đang chuyển anh/chị tới nhân viên hỗ trợ.',
          kind: 'handoff',
          reason: 'customer_requested',
        },
        sessionId: 'conversation-1',
        turnId: accepted.turnId,
        usage: { costMicros: 10_000, modelTokens: 100 },
      }),
    ).resolves.toMatchObject({ outcome: 'handed_off' });
    const page = await service.listPublicEvents({
      accessScope: publicScope,
      afterCursor: 'event-v1:2',
      sessionId: 'conversation-1',
    });
    expect(page.events[0]).toMatchObject({
      payload: { handoffId: 'handoff-1' },
      type: 'handoff.requested',
    });
  });

  it('closes an open session and reports it through getRuntimeStatus', async () => {
    const { service } = createHarness();

    const closed = await service.closeSession({
      accessScope: publicScope,
      expectedVersion: 0,
      sessionId: 'conversation-1',
    });

    expect(closed.conversationVersion).toBe(1);
    await expect(
      service.getRuntimeStatus({
        accessScope: publicScope,
        sessionId: 'conversation-1',
      }),
    ).resolves.toEqual({ conversationVersion: 1, status: 'closed' });
  });

  it('does not close another accessor’s conversation', async () => {
    const { service } = createHarness();

    await expect(
      service.closeSession({
        accessScope: wrongPublicScope,
        expectedVersion: 0,
        sessionId: 'conversation-1',
      }),
    ).rejects.toThrow(ConversationRuntimeNotFoundError);
  });

  it('rejects closing with a stale expected version', async () => {
    const { service } = createHarness();
    await service.acceptMessage(message);

    await expect(
      service.closeSession({
        accessScope: publicScope,
        expectedVersion: 0,
        sessionId: 'conversation-1',
      }),
    ).rejects.toThrow(ConversationVersionConflictError);
  });

  it('allocates the handoff ID inside the API boundary for an explicit customer request', async () => {
    const { service } = createHarness();

    const requested = await service.requestHandoff({
      accessScope: publicScope,
      expectedVersion: 0,
      sessionId: 'conversation-1',
    });

    expect(requested.handoffId).toBe('handoff-1');
    await expect(
      service.getRuntimeStatus({
        accessScope: publicScope,
        sessionId: 'conversation-1',
      }),
    ).resolves.toEqual({ conversationVersion: 1, status: 'handoff' });
    const page = await service.listPublicEvents({
      accessScope: publicScope,
      afterCursor: null,
      sessionId: 'conversation-1',
    });
    expect(page.events[0]).toMatchObject({
      payload: { handoffId: 'handoff-1', reason: 'customer_requested' },
      type: 'handoff.requested',
    });
  });

  it('does not request handoff for another accessor’s conversation', async () => {
    const { service } = createHarness();

    await expect(
      service.requestHandoff({
        accessScope: wrongPublicScope,
        expectedVersion: 0,
        sessionId: 'conversation-1',
      }),
    ).rejects.toThrow(ConversationRuntimeNotFoundError);
  });

  it('rejects requesting handoff with a stale expected version', async () => {
    const { service } = createHarness();
    await service.acceptMessage(message);

    await expect(
      service.requestHandoff({
        accessScope: publicScope,
        expectedVersion: 0,
        sessionId: 'conversation-1',
      }),
    ).rejects.toThrow(ConversationVersionConflictError);
  });
});
