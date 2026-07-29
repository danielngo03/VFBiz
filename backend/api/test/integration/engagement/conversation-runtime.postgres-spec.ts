import { createHash, randomUUID } from 'node:crypto';
import { ConfigService } from '@nestjs/config';
import { Prisma } from '../../../src/generated/prisma/client';
import { PrismaService } from '../../../src/platform/database/prisma.service';
import { ConversationContentCipher } from '../../../src/platform/security/conversation-content-cipher';
import { parseConversationContentKeyring } from '../../../src/platform/security/conversation-content-keyring';
import {
  ConversationRuntimeClock,
  ConversationRuntimeIdGenerator,
} from '../../../src/modules/engagement/application/runtime/conversation-runtime.repository';
import {
  ConversationEventReplayRequiredError,
  ConversationMessageIdempotencyConflictError,
  ConversationRuntimeService,
} from '../../../src/modules/engagement/application/runtime/conversation-runtime.service';
import { ConversationVersionConflictError } from '../../../src/modules/engagement/domain/runtime/conversation-runtime';
import { watchConversationEvents } from '../../../src/modules/engagement/presentation/conversation-event-stream';
import {
  ConversationRuntimePersistenceCorruptionError,
  PrismaConversationRuntimeRepository,
} from '../../../src/modules/engagement/infrastructure/persistence/prisma-conversation-runtime.repository';
import { PrismaConversationSessionRepository } from '../../../src/modules/engagement/infrastructure/persistence/prisma-conversation-session.repository';

const databaseUrl = process.env.VFBIZ_TEST_DATABASE_URL;
const describeWithDatabase =
  databaseUrl === undefined ? describe.skip : describe;
const capabilityHash = 'a'.repeat(64);
const accessScope = {
  capabilityHash,
  kind: 'public_capability',
  profile: 'public_customer',
} as const;

function authorizationContextDigest(scope: typeof accessScope): string {
  return createHash('sha256')
    .update(
      JSON.stringify({
        authorityRef: scope.capabilityHash,
        kind: scope.kind,
        profile: scope.profile,
      }),
      'utf8',
    )
    .digest('hex');
}

class FixedClock extends ConversationRuntimeClock {
  now(): Date {
    return new Date('2026-07-25T08:00:00.000Z');
  }
}

class UuidIds extends ConversationRuntimeIdGenerator {
  nextId(): string {
    return randomUUID();
  }
}

describeWithDatabase('Conversation Runtime PostgreSQL integration', () => {
  let prisma: PrismaService;
  let cipher: ConversationContentCipher;
  let repository: PrismaConversationRuntimeRepository;
  let sessions: PrismaConversationSessionRepository;
  let service: ConversationRuntimeService;

  beforeAll(async () => {
    prisma = new PrismaService(
      new ConfigService({
        NODE_ENV: 'test',
        VFBIZ_DATABASE_URL: databaseUrl,
      }),
    );
    await prisma.$connect();
    cipher = new ConversationContentCipher(
      parseConversationContentKeyring(
        'integration-key',
        JSON.stringify({
          keys: [
            {
              id: 'integration-key',
              material: Buffer.alloc(32, 4).toString('base64'),
            },
          ],
        }),
      ),
    );
    repository = new PrismaConversationRuntimeRepository(prisma, cipher);
    sessions = new PrismaConversationSessionRepository(prisma, cipher);
    service = new ConversationRuntimeService(
      repository,
      new FixedClock(),
      new UuidIds(),
    );
  });

  afterAll(async () => prisma.$disconnect());

  beforeEach(async () => {
    const records = await prisma.conversationSession.findMany({
      select: { id: true },
      where: { policyRevision: 'integration-chat-policy-v1' },
    });
    if (records.length > 0) {
      await prisma.supportHandoff.deleteMany({
        where: { conversationSessionId: { in: records.map(({ id }) => id) } },
      });
      await prisma.conversationSession.deleteMany({
        where: { id: { in: records.map(({ id }) => id) } },
      });
    }
  });

  async function createSession(
    retentionUntil = new Date('2026-07-26T00:00:00Z'),
    sessionCapabilityHash = capabilityHash,
  ) {
    const id = randomUUID();
    await sessions.createSession({
      capabilityHash: sessionCapabilityHash,
      customerSubject: null,
      expiresAt: new Date('2026-07-25T12:00:00Z'),
      id,
      initialCostBudgetMicros: 2_000_000,
      initialModelTokenBudget: 20_000,
      locale: 'vi',
      release: {
        activationEnvelopeSha256: 'b'.repeat(64),
        activationId: 'integration-release-v1',
        effectiveAt: new Date('2026-07-24T00:00:00Z'),
        expiresAt: new Date('2099-07-24T00:00:00Z'),
        graphRevision: 'integration-graph-v1',
        knowledgeRevision: 'integration-knowledge-v1',
        manifestSha256: 'a'.repeat(64),
        pointerRevision: 1,
        policyRevision: 'integration-chat-policy-v1',
      },
      profile: 'public_customer',
      retentionUntil,
    });
    return id;
  }

  it('persists authority-confirmed context and exposes only active session entities', async () => {
    const sessionId = await createSession();
    const confirmedAt = new Date('2026-07-25T07:00:00.000Z');
    await expect(
      repository.confirmContextEntity({
        accessScope,
        correlationId: randomUUID(),
        entity: {
          authority: 'vehicle-catalog',
          classification: 'non_sensitive',
          confirmedAt,
          expiresAt: new Date('2026-07-25T11:00:00.000Z'),
          kind: 'vehicle_model',
          opaqueReference: 'vf-8',
          provenanceDigest: 'c'.repeat(64),
          sourceRevision: 'd'.repeat(64),
        },
        expectedVersion: 0,
        now: new Date('2026-07-25T08:00:00.000Z'),
        sessionId,
      }),
    ).resolves.toEqual({ outcome: 'confirmed' });
    await expect(
      repository.confirmContextEntity({
        accessScope,
        correlationId: randomUUID(),
        entity: {
          authority: 'vehicle-catalog',
          classification: 'non_sensitive',
          confirmedAt,
          expiresAt: new Date('2026-07-25T11:00:00.000Z'),
          kind: 'vehicle_model',
          opaqueReference: 'vf-9',
          provenanceDigest: 'c'.repeat(64),
          sourceRevision: 'd'.repeat(64),
        },
        expectedVersion: 1,
        now: new Date('2026-07-25T08:00:00.000Z'),
        sessionId,
      }),
    ).resolves.toEqual({ actualVersion: 0, outcome: 'version-conflict' });
    await expect(
      repository.confirmContextEntity({
        accessScope: { ...accessScope, capabilityHash: 'f'.repeat(64) },
        correlationId: randomUUID(),
        entity: {
          authority: 'vehicle-catalog',
          classification: 'non_sensitive',
          confirmedAt,
          expiresAt: new Date('2026-07-25T11:00:00.000Z'),
          kind: 'vehicle_model',
          opaqueReference: 'vf-9',
          provenanceDigest: 'e'.repeat(64),
          sourceRevision: 'd'.repeat(64),
        },
        expectedVersion: 0,
        now: new Date('2026-07-25T08:00:00.000Z'),
        sessionId,
      }),
    ).resolves.toEqual({ outcome: 'not-found' });
    await expect(
      repository.confirmContextEntity({
        accessScope,
        correlationId: randomUUID(),
        entity: {
          authority: 'vehicle-catalog',
          classification: 'non_sensitive',
          confirmedAt: new Date('2026-07-25T07:30:00.000Z'),
          expiresAt: new Date('2026-07-25T11:00:00.000Z'),
          kind: 'vehicle_model',
          opaqueReference: 'vf-9',
          provenanceDigest: 'e'.repeat(64),
          sourceRevision: 'f'.repeat(64),
        },
        expectedVersion: 0,
        now: new Date('2026-07-25T08:00:00.000Z'),
        sessionId,
      }),
    ).resolves.toEqual({ outcome: 'confirmed' });
    await expect(
      repository.confirmContextEntity({
        accessScope,
        correlationId: randomUUID(),
        entity: {
          authority: 'vehicle-catalog',
          classification: 'non_sensitive',
          confirmedAt: new Date('2026-07-25T07:15:00.000Z'),
          expiresAt: new Date('2026-07-25T11:00:00.000Z'),
          kind: 'vehicle_model',
          opaqueReference: 'vf-7',
          provenanceDigest: 'a'.repeat(64),
          sourceRevision: 'b'.repeat(64),
        },
        expectedVersion: 0,
        now: new Date('2026-07-25T08:00:00.000Z'),
        sessionId,
      }),
    ).resolves.toEqual({ outcome: 'stale' });
    await expect(
      repository.confirmContextEntity({
        accessScope,
        correlationId: randomUUID(),
        entity: {
          authority: 'vehicle-catalog',
          classification: 'non_sensitive',
          confirmedAt: new Date('2026-07-25T08:06:00.000Z'),
          expiresAt: new Date('2026-07-25T11:00:00.000Z'),
          kind: 'vehicle_model',
          opaqueReference: 'vf-8',
          provenanceDigest: 'c'.repeat(64),
          sourceRevision: 'd'.repeat(64),
        },
        expectedVersion: 0,
        now: new Date('2026-07-25T08:00:00.000Z'),
        sessionId,
      }),
    ).rejects.toThrow('confirmation is in the future');
    await expect(
      repository.confirmContextEntity({
        accessScope,
        correlationId: randomUUID(),
        entity: {
          authority: 'vehicle-catalog',
          classification: 'non_sensitive',
          confirmedAt,
          expiresAt: new Date('2026-07-25T13:00:00.000Z'),
          kind: 'vehicle_model',
          opaqueReference: 'vf-8',
          provenanceDigest: 'c'.repeat(64),
          sourceRevision: 'd'.repeat(64),
        },
        expectedVersion: 0,
        now: new Date('2026-07-25T08:00:00.000Z'),
        sessionId,
      }),
    ).rejects.toThrow('cannot outlive its owning session');

    const accepted = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Chiếc xe lúc nãy có chính sách gì?',
      expectedVersion: 0,
      sessionId,
    });
    const claimed = await service.claimTurn({
      accessScope,
      expectedVersion: accepted.conversationVersion,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-25T09:00:00.000Z'),
      sessionId,
      turnId: accepted.turnId,
      workerId: 'context-worker',
    });
    const context = await repository.getTurnExecutionContext(
      sessionId,
      accessScope,
      accepted.turnId,
      new Date('2026-07-25T08:00:00.000Z'),
    );

    expect(context?.conversationVersion).toBe(claimed.conversationVersion);
    expect(context?.confirmedEntities).toEqual([
      expect.objectContaining({
        authority: 'vehicle-catalog',
        kind: 'vehicle_model',
        opaqueReference: 'vf-9',
      }),
    ]);
    await prisma.conversationContextEntity.updateMany({
      data: { subjectKeyHash: 'f'.repeat(64) },
      where: { conversationSessionId: sessionId },
    });
    await expect(
      repository.getTurnExecutionContext(
        sessionId,
        accessScope,
        accepted.turnId,
        new Date('2026-07-25T08:00:00.000Z'),
      ),
    ).resolves.toMatchObject({ confirmedEntities: [] });
    await expect(
      prisma.outboxEvent.findFirst({
        where: {
          aggregateId: sessionId,
          eventType: 'conversation.context.confirmed',
        },
      }),
    ).resolves.not.toBeNull();
  });

  it('enforces same-session task provenance and opaque slot envelopes in PostgreSQL', async () => {
    const firstSessionId = await createSession();
    const secondCapabilityHash = 'd'.repeat(64);
    const secondAccessScope = {
      ...accessScope,
      capabilityHash: secondCapabilityHash,
    };
    const secondSessionId = await createSession(
      new Date('2026-07-26T00:00:00Z'),
      secondCapabilityHash,
    );
    const firstTurn = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Synthetic first task message',
      expectedVersion: 0,
      sessionId: firstSessionId,
    });
    const secondTurn = await service.acceptMessage({
      accessScope: secondAccessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Synthetic second task message',
      expectedVersion: 0,
      sessionId: secondSessionId,
    });

    const insertTaskContext = (
      taskId: string,
      sourceTurnId: string | null,
      pendingSlots: unknown,
      collectedSlots: unknown,
    ) =>
      prisma.$executeRaw(
        Prisma.sql`
          INSERT INTO "conversation_task_context" (
            "conversationSessionId",
            "taskId",
            "intent",
            "intentRevision",
            "pendingSlots",
            "collectedSlots",
            "sourceTurnId",
            "taskState",
            "authorizationContextDigest",
            "assistantReleaseActivationId",
            "assistantReleaseManifestSha256",
            "graphRevision",
            "policyRevision",
            "knowledgeRevision",
            "provenanceDigest",
            "expiresAt",
            "createdAt",
            "updatedAt"
          ) VALUES (
            ${firstSessionId}::uuid,
            ${taskId}::uuid,
            'vehicle_policy',
            'router-v1',
            ${JSON.stringify(pendingSlots)}::jsonb,
            ${JSON.stringify(collectedSlots)}::jsonb,
            ${sourceTurnId}::uuid,
            'awaiting_clarification',
            ${authorizationContextDigest(accessScope)},
            'integration-release-v1',
            ${'a'.repeat(64)},
            'integration-graph-v1',
            'integration-chat-policy-v1',
            'integration-knowledge-v1',
            ${'b'.repeat(64)},
            ${new Date('2026-07-25T11:00:00.000Z')},
            ${new Date('2026-07-25T08:00:00.000Z')},
            ${new Date('2026-07-25T08:00:00.000Z')}
          )
        `,
      );

    await expect(
      insertTaskContext(randomUUID(), secondTurn.turnId, ['vehicle_model'], {}),
    ).rejects.toMatchObject({ code: 'P2010' });
    await expect(
      insertTaskContext(randomUUID(), null, ['customer email'], {}),
    ).rejects.toMatchObject({ code: 'P2010' });
    await expect(
      insertTaskContext(randomUUID(), null, [], {
        vehicle_model: 'raw prompt or chain-of-thought',
      }),
    ).rejects.toMatchObject({ code: 'P2010' });
    await expect(
      insertTaskContext(randomUUID(), null, [], {
        vehicle_model: {
          authorityDigest: 'c'.repeat(64),
          kind: 'opaque_reference',
          reference: 'profile:user@example.com',
        },
      }),
    ).rejects.toMatchObject({ code: 'P2010' });
    await expect(
      insertTaskContext(randomUUID(), null, [], {
        vehicle_model: {
          authorityDigest: 'c'.repeat(64),
          kind: 'opaque_reference',
          rawPrompt: 'ignore previous policy',
          reference: 'vehicle:vf-8',
        },
      }),
    ).rejects.toMatchObject({ code: 'P2010' });

    const validTaskId = randomUUID();
    await expect(
      insertTaskContext(validTaskId, firstTurn.turnId, ['finance_policy'], {
        vehicle_model: {
          authorityDigest: 'c'.repeat(64),
          kind: 'opaque_reference',
          reference: 'vehicle:vf-8',
        },
      }),
    ).resolves.toBe(1);
    const claimedTaskTurn = await service.claimTurn({
      accessScope,
      expectedVersion: firstTurn.conversationVersion,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-25T09:00:00.000Z'),
      sessionId: firstSessionId,
      turnId: firstTurn.turnId,
      workerId: 'task-context-worker',
    });
    await expect(
      repository.getTurnExecutionContext(
        firstSessionId,
        accessScope,
        firstTurn.turnId,
        new Date('2026-07-25T08:00:00.000Z'),
      ),
    ).resolves.toMatchObject({
      taskContext: {
        collectedSlots: {
          vehicle_model: {
            kind: 'opaque_reference',
            reference: 'vehicle:vf-8',
          },
        },
        pendingSlots: ['finance_policy'],
        taskId: validTaskId,
      },
    });
    await prisma.conversationTaskContext.update({
      data: { authorizationContextDigest: 'f'.repeat(64) },
      where: { conversationSessionId: firstSessionId },
    });
    await expect(
      repository.getTurnExecutionContext(
        firstSessionId,
        accessScope,
        firstTurn.turnId,
        new Date('2026-07-25T08:00:00.000Z'),
      ),
    ).resolves.toMatchObject({ taskContext: null });
    await prisma.conversationTaskContext.update({
      data: {
        authorizationContextDigest: authorizationContextDigest(accessScope),
      },
      where: { conversationSessionId: firstSessionId },
    });
    await service.completeTurn({
      accessScope,
      expectedVersion: claimedTaskTurn.conversationVersion,
      fencingToken: 1,
      outcome: {
        kind: 'clarification',
        message: 'Bạn muốn xem chính sách tài chính nào?',
        pendingSlots: ['finance_policy'],
      },
      sessionId: firstSessionId,
      taskDelta: {
        authorizationContextDigest: authorizationContextDigest(accessScope),
        collectedSlots: {
          vehicle_model: {
            authorityDigest: 'c'.repeat(64),
            kind: 'opaque_reference',
            reference: 'vehicle:vf-8',
          },
        },
        expectedTaskVersion: 1,
        expiresAt: new Date('2026-07-25T11:30:00.000Z'),
        intent: 'vehicle_policy',
        intentRevision: 'router-v1',
        nextState: 'awaiting_clarification',
        operation: 'upsert',
        pendingSlots: ['finance_policy'],
        provenanceDigest: 'e'.repeat(64),
        release: {
          activationId: 'integration-release-v1',
          graphRevision: 'integration-graph-v1',
          knowledgeRevision: 'integration-knowledge-v1',
          manifestSha256: 'a'.repeat(64),
          policyRevision: 'integration-chat-policy-v1',
        },
        sourceTurnId: firstTurn.turnId,
        taskId: validTaskId,
      },
      turnId: firstTurn.turnId,
      usage: { costMicros: 10, modelTokens: 5 },
    });
    await expect(
      prisma.conversationTaskContext.findUniqueOrThrow({
        where: { conversationSessionId: firstSessionId },
      }),
    ).resolves.toMatchObject({
      lastFencingToken: 1n,
      provenanceDigest: 'e'.repeat(64),
      taskVersion: 2n,
    });
    await expect(
      prisma.outboxEvent.findFirst({
        where: {
          aggregateId: firstSessionId,
          eventType: 'conversation.task.updated',
        },
      }),
    ).resolves.not.toBeNull();

    const afterClarification = await repository.getSnapshot(
      firstSessionId,
      accessScope,
      new Date('2026-07-25T08:00:00.000Z'),
    );
    expect(afterClarification).not.toBeNull();
    const topicSwitchTurn = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Tôi muốn chuyển sang chủ đề khác',
      expectedVersion: afterClarification!.version,
      sessionId: firstSessionId,
    });
    const claimedTopicSwitch = await service.claimTurn({
      accessScope,
      expectedVersion: topicSwitchTurn.conversationVersion,
      fencingToken: 2,
      leaseExpiresAt: new Date('2026-07-25T09:00:00.000Z'),
      sessionId: firstSessionId,
      turnId: topicSwitchTurn.turnId,
      workerId: 'task-context-worker',
    });
    const topicSwitchTaskId = randomUUID();
    await service.completeTurn({
      accessScope,
      expectedVersion: claimedTopicSwitch.conversationVersion,
      fencingToken: 2,
      outcome: {
        kind: 'clarification',
        message: 'Bạn muốn tìm trạm sạc ở khu vực nào?',
        pendingSlots: ['market'],
      },
      sessionId: firstSessionId,
      taskDelta: {
        authorizationContextDigest: authorizationContextDigest(accessScope),
        collectedSlots: {},
        expectedTaskVersion: 0,
        expiresAt: new Date('2026-07-25T11:30:00.000Z'),
        intent: 'charging_question',
        intentRevision: 'router-v1',
        nextState: 'awaiting_clarification',
        operation: 'upsert',
        pendingSlots: ['market'],
        provenanceDigest: 'f'.repeat(64),
        release: {
          activationId: 'integration-release-v1',
          graphRevision: 'integration-graph-v1',
          knowledgeRevision: 'integration-knowledge-v1',
          manifestSha256: 'a'.repeat(64),
          policyRevision: 'integration-chat-policy-v1',
        },
        sourceTurnId: topicSwitchTurn.turnId,
        taskId: topicSwitchTaskId,
      },
      turnId: topicSwitchTurn.turnId,
      usage: { costMicros: 10, modelTokens: 5 },
    });
    await expect(
      prisma.conversationTaskContext.findUniqueOrThrow({
        where: { conversationSessionId: firstSessionId },
      }),
    ).resolves.toMatchObject({
      lastFencingToken: 2n,
      taskId: topicSwitchTaskId,
      taskState: 'awaiting_clarification',
      taskVersion: 1n,
    });
    const topicSwitchEvent = await prisma.outboxEvent.findFirstOrThrow({
      orderBy: { createdAt: 'desc' },
      where: {
        aggregateId: firstSessionId,
        eventType: 'conversation.task.updated',
      },
    });
    expect(topicSwitchEvent.payload).toMatchObject({
      replacedTaskId: validTaskId,
      replacementReason: 'topic_switch',
    });

    const afterTopicSwitch = await repository.getSnapshot(
      firstSessionId,
      accessScope,
      new Date('2026-07-25T08:00:00.000Z'),
    );
    expect(afterTopicSwitch).not.toBeNull();
    const closeTurn = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Đóng yêu cầu hiện tại',
      expectedVersion: afterTopicSwitch!.version,
      sessionId: firstSessionId,
    });
    const claimedCloseTurn = await service.claimTurn({
      accessScope,
      expectedVersion: closeTurn.conversationVersion,
      fencingToken: 3,
      leaseExpiresAt: new Date('2026-07-25T09:00:00.000Z'),
      sessionId: firstSessionId,
      turnId: closeTurn.turnId,
      workerId: 'task-context-worker',
    });
    await service.completeTurn({
      accessScope,
      expectedVersion: claimedCloseTurn.conversationVersion,
      fencingToken: 3,
      outcome: { kind: 'refusal', message: 'Đã đóng yêu cầu hiện tại.' },
      sessionId: firstSessionId,
      taskDelta: {
        authorizationContextDigest: authorizationContextDigest(accessScope),
        collectedSlots: {},
        expectedTaskVersion: 1,
        expiresAt: new Date('2026-07-25T11:30:00.000Z'),
        intent: 'charging_question',
        intentRevision: 'router-v1',
        nextState: 'closed',
        operation: 'close',
        pendingSlots: [],
        provenanceDigest: '8'.repeat(64),
        release: {
          activationId: 'integration-release-v1',
          graphRevision: 'integration-graph-v1',
          knowledgeRevision: 'integration-knowledge-v1',
          manifestSha256: 'a'.repeat(64),
          policyRevision: 'integration-chat-policy-v1',
        },
        sourceTurnId: closeTurn.turnId,
        taskId: topicSwitchTaskId,
      },
      turnId: closeTurn.turnId,
      usage: { costMicros: 10, modelTokens: 5 },
    });

    const afterClose = await repository.getSnapshot(
      firstSessionId,
      accessScope,
      new Date('2026-07-25T08:00:00.000Z'),
    );
    expect(afterClose).not.toBeNull();
    const replacementTurn = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Tôi muốn hỏi về trạm sạc',
      expectedVersion: afterClose!.version,
      sessionId: firstSessionId,
    });
    const claimedReplacement = await service.claimTurn({
      accessScope,
      expectedVersion: replacementTurn.conversationVersion,
      fencingToken: 4,
      leaseExpiresAt: new Date('2026-07-25T09:00:00.000Z'),
      sessionId: firstSessionId,
      turnId: replacementTurn.turnId,
      workerId: 'task-context-worker',
    });
    const replacementTaskId = randomUUID();
    await service.completeTurn({
      accessScope,
      expectedVersion: claimedReplacement.conversationVersion,
      fencingToken: 4,
      outcome: {
        kind: 'clarification',
        message: 'Bạn muốn tìm trạm sạc ở khu vực nào?',
        pendingSlots: ['market'],
      },
      sessionId: firstSessionId,
      taskDelta: {
        authorizationContextDigest: authorizationContextDigest(accessScope),
        collectedSlots: {},
        expectedTaskVersion: 0,
        expiresAt: new Date('2026-07-25T11:30:00.000Z'),
        intent: 'charging_question',
        intentRevision: 'router-v1',
        nextState: 'awaiting_clarification',
        operation: 'upsert',
        pendingSlots: ['market'],
        provenanceDigest: '9'.repeat(64),
        release: {
          activationId: 'integration-release-v1',
          graphRevision: 'integration-graph-v1',
          knowledgeRevision: 'integration-knowledge-v1',
          manifestSha256: 'a'.repeat(64),
          policyRevision: 'integration-chat-policy-v1',
        },
        sourceTurnId: replacementTurn.turnId,
        taskId: replacementTaskId,
      },
      turnId: replacementTurn.turnId,
      usage: { costMicros: 10, modelTokens: 5 },
    });
    await expect(
      prisma.conversationTaskContext.findUniqueOrThrow({
        where: { conversationSessionId: firstSessionId },
      }),
    ).resolves.toMatchObject({
      lastFencingToken: 4n,
      taskId: replacementTaskId,
      taskState: 'awaiting_clarification',
      taskVersion: 1n,
    });
    const replacementEvent = await prisma.outboxEvent.findFirstOrThrow({
      orderBy: { createdAt: 'desc' },
      where: {
        aggregateId: firstSessionId,
        eventType: 'conversation.task.updated',
      },
    });
    expect(
      (replacementEvent.payload as Record<string, unknown>).replacedTaskId,
    ).toBe(topicSwitchTaskId);
    expect(replacementEvent.payload).toMatchObject({
      replacementReason: 'terminal_or_stale',
    });
  });

  it('atomically persists an encrypted inbox turn and replay-safe idempotency', async () => {
    const sessionId = await createSession();
    const content = 'Synthetic private customer message';
    const command = {
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content,
      expectedVersion: 0,
      sessionId,
    };

    const [left, right] = await Promise.all([
      service.acceptMessage(command),
      service.acceptMessage(command),
    ]);

    expect([left.replayed, right.replayed].sort()).toEqual([false, true]);
    expect(left.turnId).toBe(right.turnId);
    const persisted = await prisma.conversationMessage.findUniqueOrThrow({
      where: { id: left.turnId },
    });
    expect(persisted.redactedContent).toBeNull();
    expect(JSON.stringify(persisted.contentEnvelope)).not.toContain(content);
    const contentDigest = createHash('sha256')
      .update(
        JSON.stringify({
          budget: {
            maxCostMicros: command.budget.maxCostMicros,
            maxModelTokens: command.budget.maxModelTokens,
          },
          content,
        }),
        'utf8',
      )
      .digest('hex');
    const persistedTurn = await prisma.conversationTurn.findUniqueOrThrow({
      where: { id: left.turnId },
    });
    expect(persisted.idempotencyKeyHash).toBeNull();
    expect(
      JSON.stringify(persistedTurn.requestFingerprintEnvelope),
    ).not.toContain(contentDigest);
    await expect(
      repository.getSnapshot(sessionId, accessScope, new FixedClock().now()),
    ).resolves.toMatchObject({
      turns: [{ content, status: 'accepted' }],
      version: 1,
    });
    const reconstructedScope = {
      profile: 'public_customer',
      kind: 'public_capability',
      capabilityHash,
    } as const;
    await expect(
      sessions.listMessages(sessionId, reconstructedScope),
    ).resolves.toMatchObject([{ content, role: 'customer' }]);
  });

  it('rejects idempotency-key reuse with different content', async () => {
    const sessionId = await createSession();
    const clientMessageId = randomUUID();
    const base = {
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId,
      content: 'First synthetic message',
      expectedVersion: 0,
      sessionId,
    };
    await service.acceptMessage(base);

    await expect(
      service.acceptMessage({
        ...base,
        content: 'Different synthetic message',
        expectedVersion: 1,
      }),
    ).rejects.toBeInstanceOf(ConversationMessageIdempotencyConflictError);
  });

  it('uses OCC, one active claim and fencing to reject a late result', async () => {
    const sessionId = await createSession();
    const accepted = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Synthetic routing request',
      expectedVersion: 0,
      sessionId,
    });
    const claimed = await service.claimTurn({
      accessScope,
      expectedVersion: accepted.conversationVersion,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-25T08:05:00.000Z'),
      sessionId,
      turnId: accepted.turnId,
      workerId: 'integration-worker',
    });
    const cancelled = await service.cancelTurnByCustomer({
      accessScope,
      expectedVersion: claimed.conversationVersion,
      sessionId,
      turnId: accepted.turnId,
    });
    await expect(
      prisma.conversationTurn.findUniqueOrThrow({
        where: { id: accepted.turnId },
      }),
    ).resolves.toMatchObject({
      cancellationAuthority: 'customer',
      cancellationReason: 'user_interrupt',
      // The claim-shape check constraint requires fencingToken/workerId/
      // leaseExpiresAt to be null once status leaves 'claimed'; the token
      // is preserved for dispatch through the separate cancellation-
      // dispatch outbox, asserted further below, not on this row.
      fencingToken: null,
      leaseExpiresAt: null,
      status: 'cancelled',
      usedCostMicros: BigInt(100_000),
      usedModelTokens: BigInt(1_000),
      workerId: null,
    });
    await expect(
      prisma.conversationRuntime.findUniqueOrThrow({
        where: { conversationSessionId: sessionId },
      }),
    ).resolves.toMatchObject({
      remainingCostMicros: BigInt(1_900_000),
      remainingModelTokens: BigInt(19_000),
    });
    const cancellations = await repository.claimCancellationDispatches(
      new Date(Date.now() + 1_000),
      new Date(Date.now() + 21_000),
      10,
    );
    expect(cancellations).toEqual([
      expect.objectContaining({
        conversationVersion: claimed.conversationVersion,
        fencingToken: 1,
        reason: 'user_interrupt',
        sessionId,
        turnId: accepted.turnId,
      }),
    ]);
    await repository.completeCancellationDispatch(cancellations[0].dispatchId);
    await expect(
      prisma.outboxEvent.findUniqueOrThrow({
        where: { id: cancellations[0].dispatchId },
      }),
    ).resolves.toMatchObject({ status: 'completed' });

    await expect(
      service.completeTurn({
        accessScope,
        expectedVersion: cancelled.conversationVersion,
        fencingToken: claimed.fencingToken,
        outcome: { kind: 'refusal', message: 'Synthetic refusal' },
        sessionId,
        turnId: accepted.turnId,
        usage: { costMicros: 1, modelTokens: 1 },
      }),
    ).rejects.toBeDefined();
    await expect(
      service.acceptMessage({
        accessScope,
        budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
        clientMessageId: randomUUID(),
        content: 'Stale expected version',
        expectedVersion: 0,
        sessionId,
      }),
    ).rejects.toBeInstanceOf(ConversationVersionConflictError);
  });

  it('persists encrypted public events and purges expired sessions', async () => {
    const sessionId = await createSession(new Date('2026-07-25T09:00:00.000Z'));
    const accepted = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Synthetic event message',
      expectedVersion: 0,
      sessionId,
    });

    await expect(
      service.listPublicEvents({
        accessScope,
        afterCursor: null,
        sessionId,
      }),
    ).resolves.toMatchObject({
      events: [
        { payload: { turnId: accepted.turnId }, type: 'message.accepted' },
      ],
    });
    const storedEvent = await prisma.conversationPublicEvent.findFirstOrThrow({
      where: { conversationSessionId: sessionId },
    });
    expect(JSON.stringify(storedEvent.payloadEnvelope)).not.toContain(
      accepted.turnId,
    );

    await expect(
      repository.purgeExpiredSessions(
        new Date('2026-07-25T10:00:00.000Z'),
        100,
      ),
    ).resolves.toBe(1);
    await expect(
      prisma.conversationSession.findUnique({ where: { id: sessionId } }),
    ).resolves.toBeNull();
  });

  it('closes a session with no owning turn and keeps it readable afterward', async () => {
    const sessionId = await createSession();
    const accepted = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Message before closing',
      expectedVersion: 0,
      sessionId,
    });

    const closed = await service.closeSession({
      accessScope,
      expectedVersion: accepted.conversationVersion,
      sessionId,
    });

    expect(closed.conversationVersion).toBe(2);
    await expect(
      service.getRuntimeStatus({ accessScope, sessionId }),
    ).resolves.toEqual({ conversationVersion: 2, status: 'closed' });
    await expect(
      service.listPublicEvents({ accessScope, afterCursor: null, sessionId }),
    ).resolves.toMatchObject({
      events: [
        { payload: { turnId: accepted.turnId }, type: 'message.accepted' },
        { payload: {}, type: 'session.closed' },
      ],
    });
    const storedClosedEvent =
      await prisma.conversationPublicEvent.findFirstOrThrow({
        where: { conversationSessionId: sessionId, type: 'session.closed' },
      });
    expect(storedClosedEvent.conversationTurnId).toBeNull();
    // Sessions.listMessages depends only on ConversationSession.status
    // ('active'), a separate access-level field this transition never
    // touches — closing stops new activity without revoking read access.
    await expect(
      sessions.listMessages(sessionId, accessScope),
    ).resolves.toHaveLength(1);
    await expect(
      service.acceptMessage({
        accessScope,
        budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
        clientMessageId: randomUUID(),
        content: 'Message after closing',
        expectedVersion: closed.conversationVersion,
        sessionId,
      }),
    ).rejects.toThrow('Conversation is in closed state.');
  });

  it('polls a live message into an already-connected event watcher', async () => {
    const sessionId = await createSession();
    const controller = new AbortController();
    const seen: string[] = [];
    const watcher = (async () => {
      for await (const streamedEvent of watchConversationEvents(service, {
        accessScope,
        afterCursor: null,
        pollIntervalMs: 20,
        sessionId,
        signal: controller.signal,
      })) {
        if (streamedEvent.kind === 'event') {
          seen.push(streamedEvent.event.type);
        }
      }
    })();

    // The watcher starts polling before anything has been accepted, proving
    // this is a live subscription rather than a one-shot read racing the
    // write below.
    await new Promise((resolve) => setTimeout(resolve, 30));
    await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Live-polled message',
      expectedVersion: 0,
      sessionId,
    });
    await new Promise((resolve) => setTimeout(resolve, 200));
    controller.abort();
    await watcher;

    expect(seen).toEqual(['message.accepted']);
  });

  it('requires a typed resync when the durable cursor predates retained events', async () => {
    const sessionId = await createSession();
    const accepted = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Synthetic cursor window',
      expectedVersion: 0,
      sessionId,
    });
    await service.claimTurn({
      accessScope,
      expectedVersion: accepted.conversationVersion,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-25T09:00:00.000Z'),
      sessionId,
      turnId: accepted.turnId,
      workerId: 'worker-1',
    });
    await prisma.conversationPublicEvent.deleteMany({
      where: { conversationSessionId: sessionId, sequence: 1n },
    });

    await expect(
      service.listPublicEvents({
        accessScope,
        afterCursor: 'event-v1:0',
        sessionId,
      }),
    ).rejects.toMatchObject({
      earliestAvailableCursor: 'event-v1:2',
      latestAvailableCursor: 'event-v1:2',
      name: ConversationEventReplayRequiredError.name,
      reason: 'cursor_expired',
    });
  });

  it('reports retention expiry instead of an empty durable replay', async () => {
    const retentionUntil = new Date('2026-07-25T09:00:00.000Z');
    const sessionId = await createSession(retentionUntil);

    await expect(
      repository.listPublicEvents(
        sessionId,
        accessScope,
        null,
        50,
        new Date('2026-07-25T09:00:00.001Z'),
      ),
    ).resolves.toMatchObject({
      outcome: 'resync-required',
      reason: 'retention_expired',
      retentionUntil,
    });
  });

  it('fails closed when an authenticated event contains an unapproved field', async () => {
    const sessionId = await createSession();
    const accepted = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Synthetic strict decoder message',
      expectedVersion: 0,
      sessionId,
    });
    const event = await prisma.conversationPublicEvent.findFirstOrThrow({
      where: { conversationSessionId: sessionId },
    });
    const ownerId = createHash('sha256')
      .update(JSON.stringify(['public_capability', capabilityHash]), 'utf8')
      .digest('hex');
    const payloadEnvelope = cipher.encrypt(
      JSON.stringify({
        clientMessageId: randomUUID(),
        rawPrompt: 'must-never-cross-public-boundary',
        receivedSequence: 1,
        turnId: accepted.turnId,
      }),
      {
        aggregateId: sessionId,
        field: 'public-event-payload',
        ownerId,
        recordId: event.id,
        securityDomain: 'customer-conversation',
        version: 1,
      },
    );
    await prisma.conversationPublicEvent.update({
      data: {
        payloadEnvelope: payloadEnvelope as unknown as Prisma.InputJsonValue,
      },
      where: { id: event.id },
    });

    await expect(
      service.listPublicEvents({
        accessScope,
        afterCursor: null,
        sessionId,
      }),
    ).rejects.toBeInstanceOf(ConversationRuntimePersistenceCorruptionError);
  });

  it('fences authenticated session creation after subject erasure', async () => {
    const issuer = `https://identity.example/${randomUUID()}`;
    const subject = randomUUID();
    const identity = await prisma.identitySubject.create({
      data: { issuer, realm: 'vfbiz-customer', subject },
    });
    const profile = await prisma.customerProfile.create({
      data: { identitySubjectId: identity.id },
    });
    const sessionId = randomUUID();
    await sessions.createSession({
      capabilityHash: null,
      customerSubject: { issuer, subject },
      expiresAt: new Date('2099-07-25T12:00:00Z'),
      id: sessionId,
      initialCostBudgetMicros: 2_000_000,
      initialModelTokenBudget: 20_000,
      locale: 'vi',
      release: {
        activationEnvelopeSha256: 'b'.repeat(64),
        activationId: 'integration-release-v1',
        effectiveAt: new Date('2026-07-24T00:00:00Z'),
        expiresAt: new Date('2099-07-24T00:00:00Z'),
        graphRevision: 'integration-graph-v1',
        knowledgeRevision: 'integration-knowledge-v1',
        manifestSha256: 'a'.repeat(64),
        pointerRevision: 1,
        policyRevision: 'integration-chat-policy-v1',
      },
      profile: 'authenticated_customer',
      retentionUntil: new Date('2099-07-26T00:00:00Z'),
    });

    await expect(
      repository.purgeCustomerSubject(randomUUID(), issuer, subject),
    ).resolves.toBe(1);
    await expect(
      sessions.createSession({
        capabilityHash: null,
        customerSubject: { issuer, subject },
        expiresAt: new Date('2099-07-25T12:00:00Z'),
        id: randomUUID(),
        initialCostBudgetMicros: 2_000_000,
        initialModelTokenBudget: 20_000,
        locale: 'vi',
        release: {
          activationEnvelopeSha256: 'b'.repeat(64),
          activationId: 'integration-release-v1',
          effectiveAt: new Date('2026-07-24T00:00:00Z'),
          expiresAt: new Date('2099-07-24T00:00:00Z'),
          graphRevision: 'integration-graph-v1',
          knowledgeRevision: 'integration-knowledge-v1',
          manifestSha256: 'a'.repeat(64),
          pointerRevision: 1,
          policyRevision: 'integration-chat-policy-v1',
        },
        profile: 'authenticated_customer',
        retentionUntil: new Date('2099-07-26T00:00:00Z'),
      }),
    ).rejects.toMatchObject({
      response: { code: 'CUSTOMER_PROFILE_UNAVAILABLE' },
    });
    await expect(
      prisma.conversationSession.findUnique({ where: { id: sessionId } }),
    ).resolves.toBeNull();

    await prisma.conversationSubjectErasureFence.deleteMany({});
    await prisma.customerProfile.delete({ where: { id: profile.id } });
    await prisma.identitySubject.delete({ where: { id: identity.id } });
  });

  it('does not purge a live claim and purges it after the lease expires', async () => {
    const sessionId = await createSession(new Date('2099-07-26T00:00:00.000Z'));
    const accepted = await service.acceptMessage({
      accessScope,
      budget: { maxCostMicros: 100_000, maxModelTokens: 1_000 },
      clientMessageId: randomUUID(),
      content: 'Synthetic retention race message',
      expectedVersion: 0,
      sessionId,
    });
    await service.claimTurn({
      accessScope,
      expectedVersion: accepted.conversationVersion,
      fencingToken: 1,
      leaseExpiresAt: new Date('2026-07-25T11:00:00.000Z'),
      sessionId,
      turnId: accepted.turnId,
      workerId: 'retention-worker',
    });
    await prisma.conversationSession.update({
      data: { retentionUntil: new Date('2026-07-25T09:00:00.000Z') },
      where: { id: sessionId },
    });

    await expect(
      repository.purgeExpiredSessions(
        new Date('2026-07-25T10:00:00.000Z'),
        100,
      ),
    ).resolves.toBe(0);
    await prisma.conversationTurn.update({
      data: { leaseExpiresAt: new Date('2026-07-25T09:30:00.000Z') },
      where: { id: accepted.turnId },
    });
    await expect(
      repository.purgeExpiredSessions(
        new Date('2026-07-25T10:00:00.000Z'),
        100,
      ),
    ).resolves.toBe(1);
  });

  it('requests a customer-initiated handoff with no owning turn and a server-owned message', async () => {
    const sessionId = await createSession();

    const requested = await service.requestHandoff({
      accessScope,
      expectedVersion: 0,
      sessionId,
    });

    expect(requested.conversationVersion).toBe(1);
    await expect(
      service.getRuntimeStatus({ accessScope, sessionId }),
    ).resolves.toEqual({ conversationVersion: 1, status: 'handoff' });
    const storedHandoffEvent =
      await prisma.conversationPublicEvent.findFirstOrThrow({
        where: { conversationSessionId: sessionId, type: 'handoff.requested' },
      });
    expect(storedHandoffEvent.conversationTurnId).toBeNull();
    const handoff = await prisma.supportHandoff.findUniqueOrThrow({
      where: { id: requested.handoffId },
    });
    expect(handoff.reasonCode).toBe('customer_requested');
    expect(handoff.status).toBe('queued');
    const messages = await sessions.listMessages(sessionId, accessScope);
    expect(messages).toHaveLength(1);
    expect(messages[0]?.role).toBe('assistant');
    expect(messages[0]?.content).not.toHaveLength(0);
  });
});
