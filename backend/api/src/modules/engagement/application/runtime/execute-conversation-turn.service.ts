import { Injectable } from '@nestjs/common';
import { createHash } from 'node:crypto';
import {
  ConversationRuntimeNotFoundError,
  ConversationRuntimeService,
} from './conversation-runtime.service';
import {
  ConversationAiTransport,
  type ConversationAiExecutionResult,
} from './conversation-ai.transport';
import {
  ConversationRuntimeClock,
  ConversationRuntimeRepository,
} from './conversation-runtime.repository';
import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';
import type {
  ConversationTaskContext,
  ConversationTaskDelta,
} from '../../domain/runtime/conversation-task-context';
import { ConversationHandoffPolicyService } from '../services/conversation-handoff-policy.service';

export type ExecuteConversationTurnResult = {
  readonly conversationVersion: number;
  readonly outcome:
    'answered' | 'clarification_required' | 'handed_off' | 'refused';
  readonly releaseRevision: string;
  readonly status: 'completed';
  readonly turnId: string;
};

/**
 * Coordinates one already-claimed turn. Durable queue ownership and claim
 * fencing remain in the Conversation Runtime; this service only bridges a
 * valid claim to the private AI execution contract and commits a customer-safe
 * terminal outcome.
 */
@Injectable()
export class ExecuteConversationTurnService {
  constructor(
    private readonly repository: ConversationRuntimeRepository,
    private readonly runtime: ConversationRuntimeService,
    private readonly transport: ConversationAiTransport,
    private readonly clock: ConversationRuntimeClock,
    private readonly handoffPolicy: ConversationHandoffPolicyService,
  ) {}

  async execute(input: {
    accessScope: ConversationAccessScope;
    correlationId: string;
    deadlineAt: Date;
    requestId: string;
    sessionId: string;
    signal?: AbortSignal;
    turnId: string;
  }): Promise<ExecuteConversationTurnResult> {
    const context = await this.repository.getTurnExecutionContext(
      input.sessionId,
      input.accessScope,
      input.turnId,
      this.clock.now(),
    );
    if (context === null) throw new ConversationRuntimeNotFoundError();

    const result = await this.transport.execute(
      {
        ...context,
        correlationId: input.correlationId,
        deadlineAt: input.deadlineAt,
        requestId: input.requestId,
      },
      input.signal,
    );
    if (
      result.outcome !== 'failed_safely' &&
      result.releaseCommitReceipt === null
    ) {
      throw new Error('AI result is missing a release-bound commit receipt.');
    }

    if (result.outcome === 'tool_proposal') {
      const completed = await this.runtime.completeTurn({
        accessScope: input.accessScope,
        assistantReleaseRevision: result.releaseRevision,
        assistantReleaseReceipt: result.releaseCommitReceipt ?? undefined,
        expectedVersion: context.conversationVersion,
        fencingToken: context.fencingToken,
        outcome: {
          kind: 'refusal',
          message:
            'Tính năng tra cứu này chưa được phát hành an toàn. Vui lòng thử lại sau.',
        },
        sessionId: input.sessionId,
        taskDelta: closeConversationTask(context.taskContext, context.turnId),
        turnId: input.turnId,
        usage: result.usage,
      });
      return {
        conversationVersion: completed.conversationVersion,
        outcome: completed.outcome,
        releaseRevision: result.releaseRevision,
        status: 'completed',
        turnId: completed.turnId,
      };
    }

    const outcome =
      result.outcome === 'handoff_recommended'
        ? this.handoffPolicy.decide({
            profile: context.assistantProfile,
            reason: result.reason,
          }) === 'handoff'
          ? {
              customerMessage: result.customerMessage,
              kind: 'handoff' as const,
              reason: result.reason,
            }
          : {
              kind: 'refusal' as const,
              message:
                'Yêu cầu chưa thể được xử lý an toàn ở thời điểm hiện tại.',
            }
        : completionProposal(result);
    const completed = await this.runtime.completeTurn({
      accessScope: context.accessScope,
      assistantReleaseRevision:
        result.outcome === 'failed_safely' ? undefined : result.releaseRevision,
      assistantReleaseReceipt: result.releaseCommitReceipt ?? undefined,
      expectedVersion: context.conversationVersion,
      fencingToken: context.fencingToken,
      outcome,
      sessionId: context.sessionId,
      taskDelta:
        result.outcome === 'clarification_required'
          ? result.taskDelta
          : result.outcome === 'failed_safely'
            ? undefined
            : closeConversationTask(context.taskContext, context.turnId),
      turnId: context.turnId,
      usage: result.usage,
    });
    return {
      conversationVersion: completed.conversationVersion,
      outcome: completed.outcome,
      releaseRevision: result.releaseRevision,
      status: 'completed',
      turnId: completed.turnId,
    };
  }

  async propagateCancellation(input: {
    accessScope: ConversationAccessScope;
    correlationId: string;
    reason:
      'budget_exhausted' | 'system_shutdown' | 'timeout' | 'user_interrupt';
    requestId: string;
    sessionId: string;
    signal?: AbortSignal;
    turnId: string;
  }): Promise<'accepted' | 'not-running'> {
    const context = await this.repository.getTurnExecutionContext(
      input.sessionId,
      input.accessScope,
      input.turnId,
      this.clock.now(),
    );
    if (context === null) return 'not-running';
    await this.transport.cancel(
      {
        accessScope: context.accessScope,
        assistantProfile: context.assistantProfile,
        authorizationContextDigest: context.authorizationContextDigest,
        budget: context.budget,
        conversationVersion: context.conversationVersion,
        correlationId: input.correlationId,
        fencingToken: context.fencingToken,
        locale: context.locale,
        release: context.release,
        policyRevision: context.policyRevision,
        reason: input.reason,
        requestId: input.requestId,
        sessionId: context.sessionId,
        turnId: context.turnId,
      },
      input.signal,
    );
    return 'accepted';
  }
}

function closeConversationTask(
  context: ConversationTaskContext | null,
  sourceTurnId: string,
): ConversationTaskDelta | undefined {
  if (context === null) return undefined;

  const material = {
    authorizationContextDigest: context.authorizationContextDigest,
    collectedSlots: context.collectedSlots,
    expectedTaskVersion: context.taskVersion,
    expiresAt: context.expiresAt.toISOString(),
    intent: context.intent,
    intentRevision: context.intentRevision,
    nextState: 'closed',
    operation: 'close',
    pendingSlots: [],
    release: context.release,
    sourceTurnId,
    taskId: context.taskId,
  } as const;
  return {
    ...material,
    expiresAt: context.expiresAt,
    provenanceDigest: createHash('sha256')
      .update(JSON.stringify(material), 'utf8')
      .digest('hex'),
  };
}

function completionProposal(
  result: Exclude<
    ConversationAiExecutionResult,
    { readonly outcome: 'tool_proposal' }
  >,
) {
  switch (result.outcome) {
    case 'answered':
      return {
        citations: result.citations,
        kind: 'answer' as const,
        message: result.message,
      };
    case 'conversational':
      return {
        citations: [],
        kind: 'answer' as const,
        message: result.message,
      };
    case 'clarification_required':
      return {
        kind: 'clarification' as const,
        message: result.message,
        pendingSlots: result.pendingSlots,
      };
    case 'refused':
      return {
        kind: 'refusal' as const,
        message: result.message,
      };
    case 'failed_safely':
      return {
        kind: 'refusal' as const,
        message: result.message,
      };
    case 'handoff_recommended':
      throw new Error('Handoff recommendations require API policy evaluation.');
  }
}
