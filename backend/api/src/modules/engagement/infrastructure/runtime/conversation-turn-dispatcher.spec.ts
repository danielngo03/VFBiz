import type { InternalAiTrustConfig } from '../../../../platform/config/internal-ai-trust.config';
import {
  ConversationAiTransportError,
  type ConversationAiTransport,
} from '../../application/runtime/conversation-ai.transport';
import type { ConversationRuntimeRepository } from '../../application/runtime/conversation-runtime.repository';
import type { ConversationRuntimeService } from '../../application/runtime/conversation-runtime.service';
import type { ExecuteConversationTurnService } from '../../application/runtime/execute-conversation-turn.service';
import { ConversationTurnDispatcher } from './conversation-turn-dispatcher';

const accessScope = {
  capabilityHash: 'a'.repeat(64),
  kind: 'public_capability',
  profile: 'public_customer',
} as const;

const clock = { now: () => new Date('2026-07-25T08:00:00.000Z') };

describe('ConversationTurnDispatcher', () => {
  it('delivers durable cancellation and dispatches an accepted turn', async () => {
    const repository = {
      claimCancellationDispatches: jest
        .fn()
        .mockResolvedValue([])
        .mockResolvedValueOnce([
          {
            accessScope,
            assistantProfile: 'public_customer',
            attempts: 1,
            budget: { maxCostMicros: 100, maxModelTokens: 100 },
            conversationVersion: 2,
            correlationId: '423e4567-e89b-42d3-a456-426614174000',
            dispatchId: '523e4567-e89b-42d3-a456-426614174000',
            fencingToken: 1,
            locale: 'vi',
            policyRevision: 'policy-r1',
            reason: 'user_interrupt',
            requestId: '523e4567-e89b-42d3-a456-426614174000',
            sessionId: '123e4567-e89b-42d3-a456-426614174000',
            turnId: '223e4567-e89b-42d3-a456-426614174000',
          },
        ]),
      completeCancellationDispatch: jest.fn().mockResolvedValue(undefined),
      findDispatchCandidates: jest
        .fn()
        .mockResolvedValue([])
        .mockResolvedValueOnce([
          {
            accessScope,
            attempts: 0,
            expectedVersion: 0,
            nextFencingToken: 1,
            sessionId: '123e4567-e89b-42d3-a456-426614174000',
            turnId: '223e4567-e89b-42d3-a456-426614174000',
          },
        ]),
      retryCancellationDispatch: jest.fn(),
    };
    const transport = { cancel: jest.fn().mockResolvedValue({}) };
    const runtime = {
      claimTurn: jest.fn().mockResolvedValue({
        conversationVersion: 1,
        fencingToken: 1,
        turnId: '223e4567-e89b-42d3-a456-426614174000',
      }),
    };
    const executor = { execute: jest.fn().mockResolvedValue({}) };
    const dispatcher = new ConversationTurnDispatcher(
      {
        dispatchEnabled: true,
        enabled: true,
        requestTimeoutMs: 1_000,
      } as InternalAiTrustConfig,
      transport as unknown as ConversationAiTransport,
      repository as unknown as ConversationRuntimeRepository,
      runtime as unknown as ConversationRuntimeService,
      executor as unknown as ExecuteConversationTurnService,
      clock,
    );

    dispatcher.onModuleInit();
    await new Promise((resolve) => setTimeout(resolve, 20));
    dispatcher.onModuleDestroy();

    expect(transport.cancel).toHaveBeenCalledTimes(1);
    expect(repository.completeCancellationDispatch).toHaveBeenCalledTimes(1);
    const cancellationClaim = repository.claimCancellationDispatches.mock
      .calls[0] as unknown as readonly [Date, Date, number];
    expect(
      cancellationClaim[1].getTime() - cancellationClaim[0].getTime(),
    ).toBe(20_000);
    expect(cancellationClaim[2]).toBe(3);
    expect(runtime.claimTurn).toHaveBeenCalledTimes(1);
    expect(executor.execute).toHaveBeenCalledTimes(1);
  });

  it('does not consume the durable inbox when execution dispatch is disabled', async () => {
    const repository = {
      claimCancellationDispatches: jest.fn(),
      findDispatchCandidates: jest.fn(),
    };
    const dispatcher = new ConversationTurnDispatcher(
      {
        dispatchEnabled: false,
        enabled: true,
        requestTimeoutMs: 60_000,
      } as InternalAiTrustConfig,
      { cancel: jest.fn() } as unknown as ConversationAiTransport,
      repository as unknown as ConversationRuntimeRepository,
      { claimTurn: jest.fn() } as unknown as ConversationRuntimeService,
      { execute: jest.fn() } as unknown as ExecuteConversationTurnService,
      clock,
    );

    dispatcher.onModuleInit();
    await new Promise((resolve) => setTimeout(resolve, 20));
    dispatcher.onModuleDestroy();

    expect(dispatcher.isEnabled()).toBe(false);
    expect(repository.claimCancellationDispatches).not.toHaveBeenCalled();
    expect(repository.findDispatchCandidates).not.toHaveBeenCalled();
  });

  it('continues delivering cancellation while all turn slots are occupied', async () => {
    const sessions = [
      '123e4567-e89b-42d3-a456-426614174000',
      '123e4567-e89b-42d3-a456-426614174001',
      '123e4567-e89b-42d3-a456-426614174002',
    ];
    const repository = {
      claimCancellationDispatches: jest
        .fn()
        .mockResolvedValue([])
        .mockResolvedValueOnce([])
        .mockResolvedValueOnce([
          {
            accessScope,
            assistantProfile: 'public_customer',
            attempts: 1,
            budget: { maxCostMicros: 100, maxModelTokens: 100 },
            conversationVersion: 2,
            correlationId: '423e4567-e89b-42d3-a456-426614174000',
            dispatchId: '523e4567-e89b-42d3-a456-426614174000',
            fencingToken: 1,
            locale: 'vi',
            policyRevision: 'policy-r1',
            reason: 'user_interrupt',
            requestId: '623e4567-e89b-42d3-a456-426614174000',
            sessionId: sessions[0],
            turnId: '223e4567-e89b-42d3-a456-426614174000',
          },
        ]),
      completeCancellationDispatch: jest.fn().mockResolvedValue(undefined),
      findDispatchCandidates: jest
        .fn()
        .mockResolvedValue([])
        .mockResolvedValueOnce(
          sessions.map((sessionId, index) => ({
            accessScope,
            attempts: 0,
            expectedVersion: 0,
            nextFencingToken: 1,
            sessionId,
            turnId: `223e4567-e89b-42d3-a456-42661417400${index}`,
          })),
        ),
      retryCancellationDispatch: jest.fn(),
    };
    const neverCompletes = new Promise<never>(() => undefined);
    const transport = { cancel: jest.fn().mockResolvedValue({}) };
    const runtime = {
      claimTurn: jest.fn().mockImplementation((input: { turnId: string }) =>
        Promise.resolve({
          conversationVersion: 1,
          fencingToken: 1,
          turnId: input.turnId,
        }),
      ),
    };
    const dispatcher = new ConversationTurnDispatcher(
      {
        dispatchEnabled: true,
        enabled: true,
        requestTimeoutMs: 1_000,
      } as InternalAiTrustConfig,
      transport as unknown as ConversationAiTransport,
      repository as unknown as ConversationRuntimeRepository,
      runtime as unknown as ConversationRuntimeService,
      {
        execute: jest.fn().mockReturnValue(neverCompletes),
      } as unknown as ExecuteConversationTurnService,
      clock,
    );

    dispatcher.onModuleInit();
    await new Promise((resolve) => setTimeout(resolve, 320));
    dispatcher.onModuleDestroy();

    expect(runtime.claimTurn).toHaveBeenCalledTimes(3);
    expect(transport.cancel).toHaveBeenCalledTimes(1);
    expect(repository.completeCancellationDispatch).toHaveBeenCalledTimes(1);
  });

  it('durably reschedules a retryable turn failure with exponential backoff', async () => {
    const repository = {
      claimCancellationDispatches: jest.fn().mockResolvedValue([]),
      findDispatchCandidates: jest
        .fn()
        .mockResolvedValue([])
        .mockResolvedValueOnce([
          {
            accessScope,
            attempts: 0,
            expectedVersion: 0,
            nextFencingToken: 1,
            sessionId: '123e4567-e89b-42d3-a456-426614174000',
            turnId: '223e4567-e89b-42d3-a456-426614174000',
          },
        ]),
      recordTurnDispatchFailure: jest.fn().mockResolvedValue(true),
    };
    const runtime = {
      claimTurn: jest.fn().mockResolvedValue({
        conversationVersion: 1,
        fencingToken: 1,
        turnId: '223e4567-e89b-42d3-a456-426614174000',
      }),
    };
    const dispatcher = new ConversationTurnDispatcher(
      {
        dispatchEnabled: true,
        enabled: true,
        requestTimeoutMs: 1_000,
      } as InternalAiTrustConfig,
      { cancel: jest.fn() } as unknown as ConversationAiTransport,
      repository as unknown as ConversationRuntimeRepository,
      runtime as unknown as ConversationRuntimeService,
      {
        execute: jest
          .fn()
          .mockRejectedValue(
            new ConversationAiTransportError('provider_unavailable', true),
          ),
      } as unknown as ExecuteConversationTurnService,
      clock,
    );

    dispatcher.onModuleInit();
    await new Promise((resolve) => setTimeout(resolve, 30));
    dispatcher.onModuleDestroy();

    expect(repository.recordTurnDispatchFailure).toHaveBeenCalledWith(
      expect.objectContaining({
        failureCode: 'provider_unavailable',
        terminal: false,
      }),
    );
  });

  it('dead-letters an exhausted retryable failure before safe completion', async () => {
    const repository = {
      claimCancellationDispatches: jest.fn().mockResolvedValue([]),
      findDispatchCandidates: jest
        .fn()
        .mockResolvedValue([])
        .mockResolvedValueOnce([
          {
            accessScope,
            attempts: 2,
            expectedVersion: 0,
            nextFencingToken: 1,
            sessionId: '123e4567-e89b-42d3-a456-426614174000',
            turnId: '223e4567-e89b-42d3-a456-426614174000',
          },
        ]),
      getTurnExecutionContext: jest.fn().mockResolvedValue({
        conversationVersion: 1,
        fencingToken: 1,
      }),
      recordTurnDispatchFailure: jest.fn().mockResolvedValue(true),
    };
    const runtime = {
      claimTurn: jest.fn().mockResolvedValue({
        conversationVersion: 1,
        fencingToken: 1,
        turnId: '223e4567-e89b-42d3-a456-426614174000',
      }),
      completeTurn: jest.fn().mockResolvedValue({}),
    };
    const dispatcher = new ConversationTurnDispatcher(
      {
        dispatchEnabled: true,
        enabled: true,
        requestTimeoutMs: 1_000,
      } as InternalAiTrustConfig,
      { cancel: jest.fn() } as unknown as ConversationAiTransport,
      repository as unknown as ConversationRuntimeRepository,
      runtime as unknown as ConversationRuntimeService,
      {
        execute: jest
          .fn()
          .mockRejectedValue(
            new ConversationAiTransportError('provider_unavailable', true),
          ),
      } as unknown as ExecuteConversationTurnService,
      clock,
    );

    dispatcher.onModuleInit();
    await new Promise((resolve) => setTimeout(resolve, 30));
    dispatcher.onModuleDestroy();

    expect(repository.recordTurnDispatchFailure).toHaveBeenCalledWith(
      expect.objectContaining({
        failureCode: 'provider_unavailable',
        terminal: true,
      }),
    );
    expect(runtime.completeTurn).toHaveBeenCalledTimes(1);
  });
});
