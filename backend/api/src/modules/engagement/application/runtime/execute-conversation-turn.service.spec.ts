import type { ConversationRuntimeService } from './conversation-runtime.service';
import type {
  ConversationRuntimeRepository,
  ConversationTurnExecutionContext,
} from './conversation-runtime.repository';
import { ExecuteConversationTurnService } from './execute-conversation-turn.service';
import { ConversationHandoffPolicyService } from '../services/conversation-handoff-policy.service';

const clock = { now: () => new Date('2026-07-25T08:00:00.000Z') };

const accessScope = {
  capabilityHash: 'a'.repeat(64),
  kind: 'public_capability' as const,
  profile: 'public_customer' as const,
};
const release = {
  activationEnvelopeSha256: 'b'.repeat(64),
  activationId: '00000000-0000-4000-8000-000000000010',
  effectiveAt: new Date('2026-07-25T00:00:00.000Z'),
  expiresAt: new Date('2026-07-26T00:00:00.000Z'),
  graphRevision: 'graph-r1',
  knowledgeRevision: 'knowledge-r1',
  manifestSha256: 'a'.repeat(64),
  pointerRevision: 1,
  policyRevision: 'policy-r1',
} as const;
const context: ConversationTurnExecutionContext = {
  accessScope,
  assistantProfile: 'public_customer',
  budget: { maxCostMicros: 10_000, maxModelTokens: 1_000 },
  content: 'Chính sách là gì?',
  conversationVersion: 4,
  fencingToken: 9,
  locale: 'vi',
  release,
  policyRevision: 'policy-r1',
  sessionId: '123e4567-e89b-42d3-a456-426614174000',
  turnId: '223e4567-e89b-42d3-a456-426614174000',
};
const releaseCommitReceipt = {
  activationEnvelopeSha256: 'b'.repeat(64),
  activationId: '00000000-0000-4000-8000-000000000010',
  candidateSha256: 'a'.repeat(64),
  conversationVersion: 4,
  expiresAt: new Date('2026-07-25T08:00:15.000Z'),
  fencingToken: 9,
  issuedAt: new Date('2026-07-25T08:00:00.000Z'),
  leaseId: '00000000-0000-4000-8000-000000000001',
  pointerRevision: 1,
  requestId: '323e4567-e89b-42d3-a456-426614174000',
  sessionId: context.sessionId,
  turnId: context.turnId,
} as const;

describe('ExecuteConversationTurnService', () => {
  it('commits a grounded result using the exact version and fence', async () => {
    const fixture = createFixture();
    fixture.transport.execute.mockResolvedValue({
      citations: [
        {
          retrievedAt: new Date('2026-07-25T08:00:00.000Z'),
          revision: 'source-r1',
          sourceId: 'source-1',
          title: 'Approved policy',
          uri: 'https://example.test/policy',
        },
      ],
      message: 'Câu trả lời có nguồn.',
      outcome: 'answered',
      releaseCommitReceipt,
      releaseRevision: '00000000-0000-4000-8000-000000000010',
      revisions: {
        graph: 'graph-r1',
        knowledge: 'knowledge-r1',
        policy: 'policy-r1',
      },
      usage: { costMicros: 100, modelTokens: 50 },
    });
    fixture.runtime.completeTurn.mockResolvedValue({
      conversationVersion: 5,
      eventCursor: 'event-v1:3',
      outcome: 'answered',
      turnId: context.turnId,
    });

    await expect(fixture.service.execute(executionInput())).resolves.toEqual({
      conversationVersion: 5,
      outcome: 'answered',
      releaseRevision: '00000000-0000-4000-8000-000000000010',
      status: 'completed',
      turnId: context.turnId,
    });
    expect(fixture.runtime.completeTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        expectedVersion: 4,
        fencingToken: 9,
        sessionId: context.sessionId,
        turnId: context.turnId,
      }),
    );
  });

  it('fails closed without creating a handoff while tool execution is unavailable', async () => {
    const fixture = createFixture();
    fixture.transport.execute.mockResolvedValue({
      arguments: { model: 'VF 8' },
      argumentsHash: 'b'.repeat(64),
      outcome: 'tool_proposal',
      releaseCommitReceipt,
      releaseRevision: '00000000-0000-4000-8000-000000000010',
      revisions: {
        graph: 'graph-r1',
        knowledge: 'knowledge-r1',
        policy: 'policy-r1',
      },
      schemaVersion: '1',
      tool: 'get_vehicle_profile',
      usage: { costMicros: 100, modelTokens: 50 },
    });
    fixture.runtime.completeTurn.mockResolvedValue({
      conversationVersion: 5,
      eventCursor: 'event-v1:3',
      outcome: 'refused',
      turnId: context.turnId,
    });

    await expect(fixture.service.execute(executionInput())).resolves.toEqual({
      conversationVersion: 5,
      outcome: 'refused',
      releaseRevision: '00000000-0000-4000-8000-000000000010',
      status: 'completed',
      turnId: context.turnId,
    });
    expect(fixture.runtime.completeTurn).toHaveBeenCalledTimes(1);
  });

  it('commits terminal clarification without converting it to handoff', async () => {
    const fixture = createFixture();
    fixture.transport.execute.mockResolvedValue({
      message: 'Vui lòng cho biết phiên bản xe.',
      outcome: 'clarification_required',
      pendingSlots: ['vehicle_variant'],
      releaseCommitReceipt,
      releaseRevision: '00000000-0000-4000-8000-000000000010',
      revisions: {
        graph: 'graph-r1',
        knowledge: 'knowledge-r1',
        policy: 'policy-r1',
      },
      usage: { costMicros: 20, modelTokens: 8 },
    });
    fixture.runtime.completeTurn.mockResolvedValue({
      conversationVersion: 5,
      eventCursor: 'event-v1:3',
      outcome: 'clarification_required',
      turnId: context.turnId,
    });

    await expect(
      fixture.service.execute(executionInput()),
    ).resolves.toMatchObject({
      outcome: 'clarification_required',
    });
    expect(fixture.runtime.completeTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        outcome: {
          kind: 'clarification',
          message: 'Vui lòng cho biết phiên bản xe.',
          pendingSlots: ['vehicle_variant'],
        },
      }),
    );
  });

  it('persists failed-safely incurred usage as a refusal', async () => {
    const fixture = createFixture();
    fixture.transport.execute.mockResolvedValue({
      code: 'RELEASE_SUPPRESSED',
      message: 'Câu trả lời đã được chặn an toàn.',
      outcome: 'failed_safely',
      releaseCommitReceipt: null,
      releaseRevision: '00000000-0000-4000-8000-000000000010',
      revisions: {
        graph: 'graph-r1',
        knowledge: 'knowledge-r1',
        policy: 'policy-r1',
      },
      usage: { costMicros: 250, modelTokens: 75 },
    });

    await fixture.service.execute(executionInput());

    expect(fixture.runtime.completeTurn).toHaveBeenCalledWith(
      expect.objectContaining({
        outcome: {
          kind: 'refusal',
          message: 'Câu trả lời đã được chặn an toàn.',
        },
        usage: { costMicros: 250, modelTokens: 75 },
      }),
    );
  });

  it('propagates cancellation only for a currently claimed turn', async () => {
    const fixture = createFixture();
    fixture.transport.cancel.mockResolvedValue({ status: 'accepted' });

    await expect(
      fixture.service.propagateCancellation({
        accessScope,
        correlationId: '423e4567-e89b-42d3-a456-426614174000',
        reason: 'user_interrupt',
        requestId: '323e4567-e89b-42d3-a456-426614174000',
        sessionId: context.sessionId,
        turnId: context.turnId,
      }),
    ).resolves.toBe('accepted');
    expect(fixture.transport.cancel).toHaveBeenCalledWith(
      expect.objectContaining({
        conversationVersion: 4,
        fencingToken: 9,
        reason: 'user_interrupt',
      }),
      undefined,
    );
  });
});

function executionInput() {
  return {
    accessScope,
    correlationId: '423e4567-e89b-42d3-a456-426614174000',
    deadlineAt: new Date(Date.now() + 30_000),
    requestId: '323e4567-e89b-42d3-a456-426614174000',
    sessionId: context.sessionId,
    turnId: context.turnId,
  };
}

function createFixture() {
  const repository = {
    getTurnExecutionContext: jest.fn().mockResolvedValue(context),
  };
  const runtime = {
    completeTurn: jest.fn().mockResolvedValue({
      conversationVersion: 5,
      eventCursor: 'cursor',
      outcome: 'handed_off',
      turnId: context.turnId,
    }),
  };
  const transport = {
    cancel: jest.fn(),
    execute: jest.fn(),
  };
  return {
    repository,
    runtime,
    service: new ExecuteConversationTurnService(
      repository as unknown as ConversationRuntimeRepository,
      runtime as unknown as ConversationRuntimeService,
      transport,
      clock,
      new ConversationHandoffPolicyService(),
    ),
    transport,
  };
}
