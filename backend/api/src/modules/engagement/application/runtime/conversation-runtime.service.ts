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
  type CompletedTurn,
  type ConversationCancellationReason,
  type ConversationCitation,
  type ConversationAccessScope,
  type ConversationHandoffReason,
  type ConversationPublicEvent,
  type CustomerSafeTurnOutcome,
  type TurnBudgetReservation,
  type TurnBudgetUsage,
} from '../../domain/runtime/conversation-runtime';
import {
  ConversationRuntimeClock,
  ConversationRuntimeIdGenerator,
  ConversationRuntimeRepository,
  type AcceptedMessageReplay,
  type ConversationRuntimeCommitResult,
} from './conversation-runtime.repository';

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

export type ConversationTurnCompletionProposal =
  | {
      readonly citations: readonly ConversationCitation[];
      readonly kind: 'answer';
      readonly message: string;
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
    const fingerprint = fingerprintMessage(input.content, input.budget);
    const existing = await this.repository.findAcceptedMessage(
      input.sessionId,
      input.accessScope,
      input.clientMessageId,
    );
    if (existing !== null) {
      return replayAcceptedMessage(existing, fingerprint, input.accessScope);
    }

    const aggregate = await this.load(input.sessionId, input.accessScope);
    const transition = aggregate.acceptMessage({
      budget: input.budget,
      clientMessageId: input.clientMessageId,
      content: input.content,
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      now: this.clock.now(),
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
    const aggregate = await this.load(input.sessionId, input.accessScope);
    const transition = aggregate.claimTurn({
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      fencingToken: input.fencingToken,
      leaseExpiresAt: input.leaseExpiresAt,
      now: this.clock.now(),
      turnId: input.turnId,
      workerId: input.workerId,
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      sessionId: input.sessionId,
    });
    assertCommitSucceeded(commit, input.expectedVersion);
    return transition.result;
  }

  async completeTurn(input: {
    accessScope: ConversationAccessScope;
    expectedVersion: number;
    fencingToken: number;
    outcome: ConversationTurnCompletionProposal;
    sessionId: string;
    turnId: string;
    usage: TurnBudgetUsage;
  }): Promise<CompletedTurn> {
    const aggregate = await this.load(input.sessionId, input.accessScope);
    const outcome: CustomerSafeTurnOutcome =
      input.outcome.kind === 'handoff'
        ? {
            ...input.outcome,
            handoffId: this.ids.nextId('handoff'),
          }
        : input.outcome;
    const transition = aggregate.completeTurn({
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      fencingToken: input.fencingToken,
      now: this.clock.now(),
      outcome,
      turnId: input.turnId,
      usage: input.usage,
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      sessionId: input.sessionId,
    });
    assertCommitSucceeded(commit, input.expectedVersion);
    return transition.result;
  }

  async cancelTurn(input: {
    accessScope: ConversationAccessScope;
    expectedVersion: number;
    fencingToken?: number;
    reason: ConversationCancellationReason;
    sessionId: string;
    turnId: string;
    usage?: TurnBudgetUsage;
  }): Promise<CancelledTurn> {
    const aggregate = await this.load(input.sessionId, input.accessScope);
    const transition = aggregate.cancelTurn({
      eventId: this.ids.nextId('event'),
      expectedVersion: input.expectedVersion,
      fencingToken: input.fencingToken,
      now: this.clock.now(),
      reason: input.reason,
      turnId: input.turnId,
      usage: input.usage,
    });
    const commit = await this.repository.commit({
      accessScope: input.accessScope,
      events: transition.events,
      expectedVersion: input.expectedVersion,
      nextState: transition.state,
      sessionId: input.sessionId,
    });
    assertCommitSucceeded(commit, input.expectedVersion);
    return transition.result;
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
    const events = await this.repository.listPublicEvents(
      input.sessionId,
      input.accessScope,
      decodePublicEventCursor(input.afterCursor),
      limit,
    );
    const safeEvents = events.map(copyConversationPublicEvent);
    return {
      events: safeEvents,
      nextCursor:
        safeEvents.length === 0 ? input.afterCursor : safeEvents.at(-1)!.cursor,
    };
  }

  private async load(sessionId: string, accessScope: ConversationAccessScope) {
    const snapshot = await this.repository.getSnapshot(sessionId, accessScope);
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
