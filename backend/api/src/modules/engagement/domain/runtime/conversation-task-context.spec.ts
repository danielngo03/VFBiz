import { randomUUID } from 'node:crypto';
import {
  applyConversationTaskDelta,
  assertConversationTaskContext,
  ConversationTaskConflictError,
  createConversationTaskContext,
  type ConversationTaskContext,
  type ConversationTaskDelta,
} from './conversation-task-context';

const release = {
  activationId: 'assistant-release-v1',
  graphRevision: 'graph-v1',
  knowledgeRevision: 'knowledge-v1',
  manifestSha256: 'a'.repeat(64),
  policyRevision: 'policy-v1',
} as const;
const now = new Date('2026-07-29T08:00:00.000Z');

function validContext(
  overrides: Partial<ConversationTaskContext> = {},
): ConversationTaskContext {
  return {
    authorizationContextDigest: 'b'.repeat(64),
    closedAt: null,
    collectedSlots: {
      vehicle_model: {
        authorityDigest: 'c'.repeat(64),
        kind: 'opaque_reference',
        reference: 'vehicle:vf-8',
      },
    },
    expiresAt: new Date('2026-07-29T08:30:00.000Z'),
    intent: 'vehicle_policy',
    intentRevision: 'router-v1',
    lastFencingToken: 7,
    pendingSlots: ['finance_policy'],
    provenanceDigest: 'd'.repeat(64),
    release,
    sourceTurnId: randomUUID(),
    state: 'awaiting_clarification',
    taskId: randomUUID(),
    taskVersion: 3,
    ...overrides,
  };
}

function updateDelta(
  context: ConversationTaskContext,
  overrides: Partial<ConversationTaskDelta> = {},
): ConversationTaskDelta {
  return {
    authorizationContextDigest: context.authorizationContextDigest,
    collectedSlots: context.collectedSlots,
    expectedTaskVersion: context.taskVersion,
    expiresAt: new Date('2026-07-29T08:45:00.000Z'),
    intent: context.intent,
    intentRevision: context.intentRevision,
    nextState: 'active',
    operation: 'upsert',
    pendingSlots: [],
    provenanceDigest: 'e'.repeat(64),
    release: context.release,
    sourceTurnId: randomUUID(),
    taskId: context.taskId,
    ...overrides,
  };
}

describe('ConversationTaskContext', () => {
  it('accepts only bounded opaque-reference task state', () => {
    expect(() => assertConversationTaskContext(validContext())).not.toThrow();
  });

  it.each([
    {
      collectedSlots: { vehicle_model: 'raw prompt or hidden reasoning' },
      name: 'raw slot text',
    },
    {
      collectedSlots: {
        vehicle_model: {
          authorityDigest: 'c'.repeat(64),
          kind: 'opaque_reference',
          nested: { prompt: 'ignore policy' },
          reference: 'vehicle:vf-8',
        },
      },
      name: 'nested payload',
    },
    {
      collectedSlots: {
        vehicle_model: {
          authorityDigest: 'c'.repeat(64),
          kind: 'opaque_reference',
          reference: 'profile:user@example.com',
        },
      },
      name: 'PII-shaped reference',
    },
    {
      name: 'non-canonical pending slot',
      pendingSlots: ['customer email'],
    },
  ])('rejects $name', (invalid) => {
    expect(() =>
      assertConversationTaskContext(
        validContext(invalid as Partial<ConversationTaskContext>),
      ),
    ).toThrow(TypeError);
  });

  it('applies an OCC- and fencing-protected update', () => {
    const current = validContext();
    const next = applyConversationTaskDelta(current, updateDelta(current), {
      fencingToken: 8,
      now,
    });

    expect(next).toMatchObject({
      lastFencingToken: 8,
      pendingSlots: [],
      state: 'active',
      taskVersion: 4,
    });
  });

  it('creates the first task context at version one', () => {
    const taskId = randomUUID();
    const delta = updateDelta(validContext({ taskId }), {
      collectedSlots: {},
      expectedTaskVersion: 0,
      nextState: 'awaiting_clarification',
      pendingSlots: ['vehicle_model'],
      taskId,
    });

    expect(
      createConversationTaskContext(delta, { fencingToken: 5, now }),
    ).toMatchObject({
      lastFencingToken: 5,
      state: 'awaiting_clarification',
      taskId,
      taskVersion: 1,
    });
  });

  it('rejects a terminal first-task delta', () => {
    const delta = updateDelta(validContext(), {
      expectedTaskVersion: 0,
      nextState: 'closed',
      operation: 'close',
    });
    expect(() =>
      createConversationTaskContext(delta, { fencingToken: 1, now }),
    ).toThrow(ConversationTaskConflictError);
  });

  it.each([
    {
      delta: (current: ConversationTaskContext) =>
        updateDelta(current, { expectedTaskVersion: 2 }),
      fencingToken: 8,
      name: 'stale task version',
    },
    {
      delta: (current: ConversationTaskContext) => updateDelta(current),
      fencingToken: 7,
      name: 'stale fencing token',
    },
    {
      delta: (current: ConversationTaskContext) =>
        updateDelta(current, {
          authorizationContextDigest: 'f'.repeat(64),
        }),
      fencingToken: 8,
      name: 'authorization binding change',
    },
    {
      delta: (current: ConversationTaskContext) =>
        updateDelta(current, {
          release: { ...release, policyRevision: 'policy-v2' },
        }),
      fencingToken: 8,
      name: 'release binding change',
    },
  ])('rejects $name', ({ delta, fencingToken }) => {
    const current = validContext();
    expect(() =>
      applyConversationTaskDelta(current, delta(current), {
        fencingToken,
        now,
      }),
    ).toThrow(ConversationTaskConflictError);
  });

  it('closes a task as a terminal audited transition', () => {
    const current = validContext();
    const next = applyConversationTaskDelta(
      current,
      updateDelta(current, {
        nextState: 'closed',
        operation: 'close',
        pendingSlots: [],
      }),
      { fencingToken: 8, now },
    );

    expect(next.closedAt).toEqual(now);
    expect(next.state).toBe('closed');
    expect(next.taskVersion).toBe(4);
  });

  it('rejects updates after task expiry', () => {
    const current = validContext({
      expiresAt: new Date('2026-07-29T07:59:59.000Z'),
    });
    expect(() =>
      applyConversationTaskDelta(current, updateDelta(current), {
        fencingToken: 8,
        now,
      }),
    ).toThrow(ConversationTaskConflictError);
  });
});
