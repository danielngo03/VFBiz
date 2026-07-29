import { createHash } from 'node:crypto';
import {
  ConversationInputValidationError,
  ConversationRuntimeAggregate,
  ConversationVersionConflictError,
  copyConversationPublicEvent,
  decodePublicEventCursor,
  sameConversationAccessScope,
  type AcceptedMessage,
  type CancelledTurn,
  type ClaimedTurn,
  type ClosedSession,
  type CompletedTurn,
  type ConversationCitation,
  type ConversationAccessScope,
  type ConversationHandoffReason,
  type ConversationPublicEvent,
  type CustomerSafeTurnOutcome,
  type RequestedHandoff,
  type TurnBudgetReservation,
  type TurnBudgetUsage,
} from '../../domain/runtime/conversation-runtime';
import type { ConversationTaskDelta } from '../../domain/runtime/conversation-task-context';
import {
  ConversationRuntimeClock,
  ConversationRuntimeIdGenerator,
  ConversationRuntimeRepository,
  type AcceptedMessageReplay,
  type ConversationRuntimeCommitResult,
} from './conversation-runtime.repository';

const EXPLICIT_HANDOFF_ACKNOWLEDGEMENT =
  'Yêu cầu hỗ trợ của bạn đã được ghi nhận. Nhân viên hỗ trợ sẽ liên hệ với bạn trong thời gian sớm nhất.';

export class ConversationRuntimeNotFoundError extends Error {
  constructor() {
    super('Conversation runtime was not found.');
    this.name = 'ConversationRuntimeNotFoundError';
  }
}

export class ConversationMessageIdempotencyConflictError extends Error {
  constructor() {
    super('Client message ID was reused for a different request.');
    this.name = 'ConversationMessageIdempotencyConflictError';
  }
}

export interface AcceptedMessageResult extends AcceptedMessage {
  readonly replayed: boolean;
}

export interface ConversationPublicEventPage {
  readonly events: readonly ConversationPublicEvent[];
  readonly nextCursor: string | null;
}

export class ConversationEventReplayRequiredError extends Error {
  constructor(
    readonly reason:
      'cursor_expired' | 'cursor_out_of_range' | 'retention_expired',
    readonly earliestAvailableCursor: string | null,
    readonly latestAvailableCursor: string | null,
    readonly retentionUntil: Date,
  ) {
    super('The durable event cursor can no longer be replayed safely.');
    this.name = 'ConversationEventReplayRequiredError';
  }
}

export interface ConversationRuntimeStatus {
  readonly conversationVersion: number;
  readonly status: 'closed' | 'handoff' | 'open';
}

export type ConversationTurnCompletionProposal =
  | {
      readonly citations: readonly ConversationCitation[];
      readonly kind: 'answer';
      readonly message: string;
    }
  | {
      readonly kind: 'clarification';
      readonly message: string;
      readonly pendingSlots: readonly string[];
    }
  | {
      readonly customerMessage: string;
      readonly kind: 'handoff';
      readonly reason: ConversationHandoffReason;
    }
  | {
      readonly kind: 'refusal';
      readonly message: string;
    };

export class ConversationRuntimeService {
  constructor(
    private readonly repository: ConversationRuntimeRepository,
    private readonly clock: ConversationRuntimeClock,
    private readonly ids: ConversationRuntimeIdGenerator,
  ) {}

  async acceptMessage(input: {
    accessScope: ConversationAccessScope;
    budget: TurnBudgetReservation;
    clientMessageId: string;
    content: string;
    expectedVersion: number;
    sessionId: string;
  }): Promise<AcceptedMessageResult> {
    const now = this.clock.now();
    const fingerprint = fingerprintMessage(input.content, input.budget);
    const existing = await this.repository.findAcceptedMessage(
      input.sessionId,
      input.accessScope,
      input.clientMessageId,
      now,
    );
    if (existing !== null) {
      return replayAcceptedMessage(existing, fingerprint, input.accessScope);
    }

    const aggregate = await this.load(input.sessionId, input.accessScope, now);
    const transition = aggregate.acceptMessage({
      budget: input.budget,
      clientMessageId: input.clientMessageId,
      content: input.content,
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      now,
      requestFingerprint: fingerprint,
      turnId: this.ids.nextId('turn'),
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      acceptedMessageReplay: {
        accessScope: input.accessScope,
        requestFingerprint: fingerprint,
        result: transition.result,
      },
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      now,
      sessionId: input.sessionId,
    });
    if (commit.outcome === 'message-replay') {
      return replayAcceptedMessage(
        commit.replay,
        fingerprint,
        input.accessScope,
      );
    }
    assertCommitSucceeded(commit, input.expectedVersion);
    return { ...transition.result, replayed: false };
  }

  async claimTurn(input: {
    accessScope: ConversationAccessScope;
    expectedVersion: number;
    fencingToken: number;
    leaseExpiresAt: Date;
    sessionId: string;
    turnId: string;
    workerId: string;
  }): Promise<ClaimedTurn> {
    const now = this.clock.now();
    const aggregate = await this.load(input.sessionId, input.accessScope, now);
    const transition = aggregate.claimTurn({
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      fencingToken: input.fencingToken,
      leaseExpiresAt: input.leaseExpiresAt,
      now,
      turnId: input.turnId,
      workerId: input.workerId,
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      now,
      sessionId: input.sessionId,
    });
    assertCommitSucceeded(commit, input.expectedVersion);
    return transition.result;
  }

  async completeTurn(input: {
    accessScope: ConversationAccessScope;
    assistantReleaseReceipt?: import('../../domain/runtime/conversation-runtime').ConversationReleaseCommitReceipt;
    assistantReleaseRevision?: string;
    expectedVersion: number;
    fencingToken: number;
    outcome: ConversationTurnCompletionProposal;
    sessionId: string;
    taskDelta?: ConversationTaskDelta;
    turnId: string;
    usage: TurnBudgetUsage;
  }): Promise<CompletedTurn> {
    const now = this.clock.now();
    const aggregate = await this.load(input.sessionId, input.accessScope, now);
    const outcome: CustomerSafeTurnOutcome =
      input.outcome.kind === 'handoff'
        ? {
            ...input.outcome,
            handoffId: this.ids.nextId('handoff'),
          }
        : input.outcome;
    const transition = aggregate.completeTurn({
      eventId: this.ids.nextId('event'),
      assistantReleaseRevision: input.assistantReleaseRevision,
      assistantReleaseReceipt: input.assistantReleaseReceipt,
      expectedVersion: input.expectedVersion,
      fencingToken: input.fencingToken,
      now,
      outcome,
      turnId: input.turnId,
      usage: input.usage,
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      now,
      sessionId: input.sessionId,
      taskDelta:
        input.taskDelta === undefined
          ? undefined
          : { delta: input.taskDelta, fencingToken: input.fencingToken },
    });
    assertCommitSucceeded(commit, input.expectedVersion);
    return transition.result;
  }

  async cancelTurnByCustomer(input: {
    accessScope: ConversationAccessScope;
    expectedVersion: number;
    sessionId: string;
    turnId: string;
  }): Promise<CancelledTurn> {
    return this.cancelTurn({
      ...input,
      authority: 'customer',
      reason: 'user_interrupt',
    });
  }

  async cancelTurnBySystem(input: {
    accessScope: ConversationAccessScope;
    expectedVersion: number;
    reason: 'budget_exhausted' | 'system_shutdown' | 'timeout';
    sessionId: string;
    turnId: string;
  }): Promise<CancelledTurn> {
    return this.cancelTurn({ ...input, authority: 'system' });
  }

  async cancelTurnByWorker(input: {
    accessScope: ConversationAccessScope;
    expectedVersion: number;
    fencingToken: number;
    reason: 'budget_exhausted' | 'system_shutdown' | 'timeout';
    sessionId: string;
    turnId: string;
    usage: TurnBudgetUsage;
  }): Promise<CancelledTurn> {
    return this.cancelTurn({ ...input, authority: 'worker' });
  }

  private async cancelTurn(input: {
    accessScope: ConversationAccessScope;
    authority: 'customer' | 'system' | 'worker';
    expectedVersion: number;
    fencingToken?: number;
    reason:
      'budget_exhausted' | 'system_shutdown' | 'timeout' | 'user_interrupt';
    sessionId: string;
    turnId: string;
    usage?: TurnBudgetUsage;
  }): Promise<CancelledTurn> {
    const now = this.clock.now();
    const aggregate = await this.load(input.sessionId, input.accessScope, now);
    const transition = aggregate.cancelTurn({
      authority: input.authority,
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      fencingToken: input.fencingToken,
      now,
      reason: input.reason,
      turnId: input.turnId,
      usage: input.usage,
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      now,
      sessionId: input.sessionId,
    });
    assertCommitSucceeded(commit, input.expectedVersion);
    return transition.result;
  }

  async closeSession(input: {
    accessScope: ConversationAccessScope;
    expectedVersion: number;
    sessionId: string;
  }): Promise<ClosedSession> {
    const now = this.clock.now();
    const aggregate = await this.load(input.sessionId, input.accessScope, now);
    const transition = aggregate.closeSession({
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      now,
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      now,
      sessionId: input.sessionId,
    });
    assertCommitSucceeded(commit, input.expectedVersion);
    return transition.result;
  }

  async requestHandoff(input: {
    accessScope: ConversationAccessScope;
    expectedVersion: number;
    sessionId: string;
  }): Promise<RequestedHandoff> {
    const now = this.clock.now();
    const aggregate = await this.load(input.sessionId, input.accessScope, now);
    const transition = aggregate.requestHandoff({
      // Fixed and API-owned, never the caller's own text: this message is
      // persisted with role "assistant" (persistCompletionProjection), the
      // same as the AI-recommended handoff path's message. Accepting
      // arbitrary client text here would let a caller spoof assistant
      // speech in the transcript.
      customerMessage: EXPLICIT_HANDOFF_ACKNOWLEDGEMENT,
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      handoffId: this.ids.nextId('handoff'),
      now,
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      now,
      sessionId: input.sessionId,
    });
    assertCommitSucceeded(commit, input.expectedVersion);
    return transition.result;
  }

  async getRuntimeStatus(input: {
    accessScope: ConversationAccessScope;
    sessionId: string;
  }): Promise<ConversationRuntimeStatus> {
    const now = this.clock.now();
    const aggregate = await this.load(input.sessionId, input.accessScope, now);
    const snapshot = aggregate.snapshot();
    return { conversationVersion: snapshot.version, status: snapshot.status };
  }

  async listPublicEvents(input: {
    accessScope: ConversationAccessScope;
    afterCursor: string | null;
    limit?: number;
    sessionId: string;
  }): Promise<ConversationPublicEventPage> {
    const limit = input.limit ?? 50;
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
      throw new ConversationInputValidationError(
        'Public event page limit must be between 1 and 100.',
      );
    }
    const read = await this.repository.listPublicEvents(
      input.sessionId,
      input.accessScope,
      decodePublicEventCursor(input.afterCursor),
      limit,
      this.clock.now(),
    );
    if (read.outcome === 'not-found') {
      return { events: [], nextCursor: input.afterCursor };
    }
    if (read.outcome === 'resync-required') {
      throw new ConversationEventReplayRequiredError(
        read.reason,
        read.earliestAvailableCursor,
        read.latestAvailableCursor,
        read.retentionUntil,
      );
    }
    const events = read.events;
    const safeEvents = events.map(copyConversationPublicEvent);
    return {
      events: safeEvents,
      nextCursor:
        safeEvents.length === 0 ? input.afterCursor : safeEvents.at(-1)!.cursor,
    };
  }

  private async load(
    sessionId: string,
    accessScope: ConversationAccessScope,
    now: Date,
  ) {
    const snapshot = await this.repository.getSnapshot(
      sessionId,
      accessScope,
      now,
    );
    if (snapshot === null) throw new ConversationRuntimeNotFoundError();
    if (!sameConversationAccessScope(snapshot.accessScope, accessScope)) {
      throw new ConversationRuntimeNotFoundError();
    }
    return ConversationRuntimeAggregate.restore(snapshot);
  }
}

const fingerprintMessage = (
  content: string,
  budget: TurnBudgetReservation,
): string =>
  createHash('sha256')
    .update(
      JSON.stringify({
        budget: {
          maxCostMicros: budget.maxCostMicros,
          maxModelTokens: budget.maxModelTokens,
        },
        content: content.trim(),
      }),
      'utf8',
    )
    .digest('hex');

const replayAcceptedMessage = (
  replay: AcceptedMessageReplay,
  fingerprint: string,
  accessScope: ConversationAccessScope,
): AcceptedMessageResult => {
  if (!sameConversationAccessScope(replay.accessScope, accessScope)) {
    throw new ConversationRuntimeNotFoundError();
  }
  if (replay.requestFingerprint !== fingerprint) {
    throw new ConversationMessageIdempotencyConflictError();
  }
  return { ...replay.result, replayed: true };
};

const assertCommitSucceeded = (
  result: ConversationRuntimeCommitResult,
  expectedVersion: number,
): void => {
  if (result.outcome === 'version-conflict') {
    throw new ConversationVersionConflictError(
      expectedVersion,
      result.actualVersion,
    );
  }
  if (result.outcome === 'message-replay') {
    throw new ConversationMessageIdempotencyConflictError();
  }
};
