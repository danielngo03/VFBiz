export const MAX_CONVERSATION_INPUT_CHARACTERS = 12_000;
export const MAX_CONVERSATION_OUTPUT_CHARACTERS = 12_000;
export const MAX_CONVERSATION_CITATIONS = 20;
export const MAX_CITATION_IDENTIFIER_CHARACTERS = 160;
export const MAX_CITATION_TITLE_CHARACTERS = 255;
export const MAX_CITATION_URI_CHARACTERS = 1_024;
export const MAX_PUBLIC_EVENT_PAYLOAD_BYTES = 60_000;
export const MAX_TURN_MODEL_TOKENS = 32_000;
export const MAX_TURN_COST_MICROS = 10_000_000;

export type ConversationCancellationReason =
  'budget_exhausted' | 'system_shutdown' | 'timeout' | 'user_interrupt';
export type ConversationCancellationAuthority =
  'customer' | 'system' | 'worker';

export type ConversationHandoffReason =
  | 'customer_requested'
  | 'insufficient_evidence'
  | 'policy_required'
  | 'safety_risk'
  | 'tool_unavailable';

export interface ConversationBudget {
  readonly remainingCostMicros: number;
  readonly remainingModelTokens: number;
}

export type ConversationContextEntityKind =
  'language' | 'market' | 'vehicle_model' | 'vehicle_variant';

export interface ConfirmedConversationContextEntity {
  readonly authority: string;
  readonly classification: 'non_sensitive';
  readonly confirmedAt: Date;
  readonly expiresAt: Date;
  readonly kind: ConversationContextEntityKind;
  readonly opaqueReference: string;
  readonly provenanceDigest: string;
  readonly sourceRevision: string;
}

export function assertConfirmedConversationContextEntity(
  entity: ConfirmedConversationContextEntity,
): void {
  const identifier = /^[a-z0-9]+(?:-[a-z0-9]+){1,7}$/;
  const digest = /^[a-f0-9]{64}$/;
  if (
    entity.classification !== 'non_sensitive' ||
    !digest.test(entity.provenanceDigest) ||
    entity.authority.length < 1 ||
    entity.authority.length > 80 ||
    !digest.test(entity.sourceRevision) ||
    !Number.isFinite(entity.confirmedAt.getTime()) ||
    !Number.isFinite(entity.expiresAt.getTime()) ||
    entity.expiresAt.getTime() <= entity.confirmedAt.getTime()
  ) {
    throw new TypeError('Invalid confirmed conversation context entity.');
  }
  if (
    ((entity.kind === 'vehicle_model' || entity.kind === 'vehicle_variant') &&
      !identifier.test(entity.opaqueReference)) ||
    (entity.kind === 'market' && !/^[A-Z]{2}$/.test(entity.opaqueReference)) ||
    (entity.kind === 'language' &&
      !['en', 'vi'].includes(entity.opaqueReference))
  ) {
    throw new TypeError('Invalid confirmed conversation context reference.');
  }
}

export type ConversationAccessScope =
  | {
      readonly capabilityHash: string;
      readonly kind: 'public_capability';
      readonly profile: 'public_customer';
    }
  | {
      readonly issuer: string;
      readonly kind: 'authenticated_customer';
      readonly profile: 'authenticated_customer';
      readonly subject: string;
    };

export interface TurnBudgetReservation {
  readonly maxCostMicros: number;
  readonly maxModelTokens: number;
}

export interface TurnBudgetUsage {
  readonly costMicros: number;
  readonly modelTokens: number;
}

export interface ConversationTurnClaim {
  readonly fencingToken: number;
  readonly leaseExpiresAt: Date;
  readonly workerId: string;
}

export interface ConversationReleaseCommitReceipt {
  readonly activationEnvelopeSha256: string;
  readonly activationId: string;
  readonly candidateSha256: string;
  readonly conversationVersion: number;
  readonly expiresAt: Date;
  readonly fencingToken: number;
  readonly issuedAt: Date;
  readonly leaseId: string;
  readonly pointerRevision: number;
  readonly requestId: string;
  readonly sessionId: string;
  readonly turnId: string;
}

export interface ConversationTurn {
  readonly assistantReleaseRevision: string | null;
  readonly assistantReleaseReceipt: ConversationReleaseCommitReceipt | null;
  readonly budget: TurnBudgetReservation;
  readonly claim: ConversationTurnClaim | null;
  readonly cancellationAuthority: ConversationCancellationAuthority | null;
  readonly cancellationReason: ConversationCancellationReason | null;
  readonly cancelledAt: Date | null;
  readonly clientMessageId: string;
  readonly content: string;
  readonly id: string;
  readonly receivedSequence: number;
  readonly requestFingerprint: string;
  readonly status:
    'accepted' | 'cancelled' | 'claimed' | 'completed' | 'handed_off';
  readonly usage: TurnBudgetUsage | null;
}

export interface ConversationRuntimeSnapshot {
  readonly accessScope: ConversationAccessScope;
  readonly budget: ConversationBudget;
  readonly fencingTokenHighWatermark: number;
  readonly id: string;
  readonly lastPublicEventSequence: number;
  readonly lastReceivedSequence: number;
  readonly status: 'closed' | 'handoff' | 'open';
  readonly turns: readonly ConversationTurn[];
  readonly version: number;
}

export interface ConversationCitation {
  readonly retrievedAt: Date;
  readonly revision: string;
  readonly sourceId: string;
  readonly title: string;
  readonly uri: string;
}

interface ConversationPublicEventBase {
  readonly cursor: string;
  readonly eventId: string;
  readonly occurredAt: Date;
  readonly sequence: number;
  readonly sessionId: string;
  readonly schemaVersion: 1;
}

export interface MessageAcceptedPublicEvent extends ConversationPublicEventBase {
  readonly payload: {
    readonly clientMessageId: string;
    readonly receivedSequence: number;
    readonly turnId: string;
  };
  readonly type: 'message.accepted';
}

export interface TurnProcessingPublicEvent extends ConversationPublicEventBase {
  readonly payload: {
    readonly turnId: string;
  };
  readonly type: 'turn.processing';
}

export interface TurnAnsweredPublicEvent extends ConversationPublicEventBase {
  readonly payload: {
    readonly citations: readonly ConversationCitation[];
    readonly message: string;
    readonly outcome: 'answered';
    readonly turnId: string;
  };
  readonly type: 'turn.completed';
}

export interface TurnRefusedPublicEvent extends ConversationPublicEventBase {
  readonly payload: {
    readonly message: string;
    readonly outcome: 'refused';
    readonly turnId: string;
  };
  readonly type: 'turn.completed';
}

export interface TurnClarificationPublicEvent extends ConversationPublicEventBase {
  readonly payload: {
    readonly message: string;
    readonly outcome: 'clarification_required';
    readonly pendingSlots: readonly string[];
    readonly turnId: string;
  };
  readonly type: 'turn.completed';
}

export interface TurnCancelledPublicEvent extends ConversationPublicEventBase {
  readonly payload: {
    readonly reason: ConversationCancellationReason;
    readonly turnId: string;
  };
  readonly type: 'turn.cancelled';
}

export interface HandoffRequestedPublicEvent extends ConversationPublicEventBase {
  readonly payload: {
    readonly customerMessage: string;
    readonly handoffId: string;
    readonly reason: ConversationHandoffReason;
    readonly status: 'queued';
    // Absent for a customer-initiated handoff requested directly on the
    // session (requestHandoff below) rather than as a turn's outcome
    // (completeTurn's handoff branch, which always supplies it).
    readonly turnId?: string;
  };
  readonly type: 'handoff.requested';
}

export interface SessionClosedPublicEvent extends ConversationPublicEventBase {
  readonly payload: Record<string, never>;
  readonly type: 'session.closed';
}

/**
 * This union is the only event shape exposed to customer transports.
 * It deliberately has no prompt, hidden reasoning, raw tool result or
 * provider response field.
 */
export type ConversationPublicEvent =
  | HandoffRequestedPublicEvent
  | MessageAcceptedPublicEvent
  | SessionClosedPublicEvent
  | TurnAnsweredPublicEvent
  | TurnCancelledPublicEvent
  | TurnClarificationPublicEvent
  | TurnProcessingPublicEvent
  | TurnRefusedPublicEvent;

export type CustomerSafeTurnOutcome =
  | {
      readonly kind: 'clarification';
      readonly message: string;
      readonly pendingSlots: readonly string[];
    }
  | {
      readonly citations: readonly ConversationCitation[];
      readonly kind: 'answer';
      readonly message: string;
    }
  | {
      readonly kind: 'handoff';
      readonly customerMessage: string;
      readonly handoffId: string;
      readonly reason: ConversationHandoffReason;
    }
  | {
      readonly kind: 'refusal';
      readonly message: string;
    };

export interface ConversationTransition<TResult> {
  readonly events: readonly ConversationPublicEvent[];
  readonly result: TResult;
  readonly state: ConversationRuntimeSnapshot;
}

export interface AcceptedMessage {
  readonly clientMessageId: string;
  readonly conversationVersion: number;
  readonly eventCursor: string;
  readonly receivedSequence: number;
  readonly turnId: string;
}

export interface ClaimedTurn {
  readonly conversationVersion: number;
  readonly eventCursor: string;
  readonly fencingToken: number;
  readonly turnId: string;
}

export interface CompletedTurn {
  readonly conversationVersion: number;
  readonly eventCursor: string;
  readonly outcome:
    'answered' | 'clarification_required' | 'handed_off' | 'refused';
  readonly turnId: string;
}

export interface CancelledTurn {
  readonly conversationVersion: number;
  readonly eventCursor: string;
  readonly reason: ConversationCancellationReason;
  readonly turnId: string;
}

export interface ClosedSession {
  readonly conversationVersion: number;
  readonly eventCursor: string;
}

export interface RequestedHandoff {
  readonly conversationVersion: number;
  readonly eventCursor: string;
  readonly handoffId: string;
}

export class ConversationInputValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConversationInputValidationError';
  }
}

export class ConversationBudgetValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConversationBudgetValidationError';
  }
}

export class ConversationBudgetExceededError extends Error {
  constructor() {
    super('The conversation does not have enough remaining budget.');
    this.name = 'ConversationBudgetExceededError';
  }
}

export class ConversationVersionConflictError extends Error {
  constructor(
    readonly expectedVersion: number,
    readonly actualVersion: number,
  ) {
    super(
      `Conversation version ${expectedVersion} does not match ${actualVersion}.`,
    );
    this.name = 'ConversationVersionConflictError';
  }
}

export class ConversationInvalidTransitionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConversationInvalidTransitionError';
  }
}

export class ConversationTurnNotFoundError extends Error {
  constructor(turnId: string) {
    super(`Conversation turn ${turnId} was not found.`);
    this.name = 'ConversationTurnNotFoundError';
  }
}

export class ConversationStaleFencingTokenError extends Error {
  constructor() {
    super('The worker fencing token is stale.');
    this.name = 'ConversationStaleFencingTokenError';
  }
}

export class ConversationCursorValidationError extends Error {
  constructor() {
    super('The public event cursor is invalid.');
    this.name = 'ConversationCursorValidationError';
  }
}

export const createConversationRuntimeSnapshot = (input: {
  accessScope: ConversationAccessScope;
  budget: ConversationBudget;
  id: string;
}): ConversationRuntimeSnapshot => {
  validateIdentifier(input.id, 'Conversation ID');
  validateAccessScope(input.accessScope);
  validateNonNegativeSafeInteger(
    input.budget.remainingModelTokens,
    'Remaining model token budget',
  );
  validateNonNegativeSafeInteger(
    input.budget.remainingCostMicros,
    'Remaining cost budget',
  );

  return {
    accessScope: copyAccessScope(input.accessScope),
    budget: { ...input.budget },
    fencingTokenHighWatermark: 0,
    id: input.id,
    lastPublicEventSequence: 0,
    lastReceivedSequence: 0,
    status: 'open',
    turns: [],
    version: 0,
  };
};

export const encodePublicEventCursor = (sequence: number): string => {
  validateNonNegativeSafeInteger(sequence, 'Public event sequence');
  return `event-v1:${sequence}`;
};

export const decodePublicEventCursor = (
  cursor: string | null,
): number | null => {
  if (cursor === null) return null;
  const match = /^event-v1:(0|[1-9]\d*)$/.exec(cursor);
  if (match === null) throw new ConversationCursorValidationError();
  const sequence = Number(match[1]);
  if (!Number.isSafeInteger(sequence)) {
    throw new ConversationCursorValidationError();
  }
  return sequence;
};

export class ConversationRuntimeAggregate {
  private constructor(private state: ConversationRuntimeSnapshot) {}

  static restore(snapshot: ConversationRuntimeSnapshot) {
    validateAccessScope(snapshot.accessScope);
    validateIdentifier(snapshot.id, 'Stored conversation ID');
    validateNonNegativeSafeInteger(snapshot.version, 'Stored version');
    validateNonNegativeSafeInteger(
      snapshot.lastReceivedSequence,
      'Stored received sequence',
    );
    validateNonNegativeSafeInteger(
      snapshot.lastPublicEventSequence,
      'Stored public event sequence',
    );
    validateNonNegativeSafeInteger(
      snapshot.fencingTokenHighWatermark,
      'Stored fencing token high watermark',
    );
    validateNonNegativeSafeInteger(
      snapshot.budget.remainingModelTokens,
      'Stored remaining model tokens',
    );
    validateNonNegativeSafeInteger(
      snapshot.budget.remainingCostMicros,
      'Stored remaining cost',
    );
    snapshot.turns.forEach((turn) => {
      validateIdentifier(turn.id, 'Stored turn ID');
      validateIdentifier(turn.clientMessageId, 'Stored client message ID');
      validateFingerprint(turn.requestFingerprint);
      validatePositiveSafeInteger(
        turn.receivedSequence,
        'Stored received sequence',
      );
      validateReservation(turn.budget);
      validateCancellationState(turn);
      if (turn.claim !== null) {
        validateDate(turn.claim.leaseExpiresAt, 'Stored turn lease expiry');
      }
      if (turn.usage !== null) validateUsage(turn.usage, turn.budget);
    });
    return new ConversationRuntimeAggregate(copySnapshot(snapshot));
  }

  snapshot(): ConversationRuntimeSnapshot {
    return copySnapshot(this.state);
  }

  acceptMessage(input: {
    budget: TurnBudgetReservation;
    clientMessageId: string;
    content: string;
    eventId: string;
    expectedVersion: number;
    now: Date;
    requestFingerprint: string;
    turnId: string;
  }): ConversationTransition<AcceptedMessage> {
    this.assertVersion(input.expectedVersion);
    this.assertOpen();
    validateDate(input.now, 'Message acceptance time');
    validateIdentifier(input.clientMessageId, 'Client message ID');
    validateIdentifier(input.turnId, 'Turn ID');
    validateIdentifier(input.eventId, 'Event ID');
    validateFingerprint(input.requestFingerprint);
    const content = validateMessageContent(input.content);
    validateReservation(input.budget);
    if (
      input.budget.maxModelTokens > this.state.budget.remainingModelTokens ||
      input.budget.maxCostMicros > this.state.budget.remainingCostMicros
    ) {
      throw new ConversationBudgetExceededError();
    }

    const receivedSequence = this.state.lastReceivedSequence + 1;
    const eventSequence = this.state.lastPublicEventSequence + 1;
    const nextVersion = this.state.version + 1;
    const event: MessageAcceptedPublicEvent = {
      cursor: encodePublicEventCursor(eventSequence),
      eventId: input.eventId,
      occurredAt: new Date(input.now.getTime()),
      payload: {
        clientMessageId: input.clientMessageId,
        receivedSequence,
        turnId: input.turnId,
      },
      schemaVersion: 1,
      sequence: eventSequence,
      sessionId: this.state.id,
      type: 'message.accepted',
    };
    const accepted: ConversationTurn = {
      assistantReleaseRevision: null,
      assistantReleaseReceipt: null,
      budget: { ...input.budget },
      cancellationAuthority: null,
      cancellationReason: null,
      cancelledAt: null,
      claim: null,
      clientMessageId: input.clientMessageId,
      content,
      id: input.turnId,
      receivedSequence,
      requestFingerprint: input.requestFingerprint,
      status: 'accepted',
      usage: null,
    };

    this.state = {
      ...this.state,
      budget: {
        remainingCostMicros:
          this.state.budget.remainingCostMicros - input.budget.maxCostMicros,
        remainingModelTokens:
          this.state.budget.remainingModelTokens - input.budget.maxModelTokens,
      },
      lastPublicEventSequence: eventSequence,
      lastReceivedSequence: receivedSequence,
      turns: [...this.state.turns, accepted],
      version: nextVersion,
    };

    return {
      events: [event],
      result: {
        clientMessageId: input.clientMessageId,
        conversationVersion: nextVersion,
        eventCursor: event.cursor,
        receivedSequence,
        turnId: input.turnId,
      },
      state: this.snapshot(),
    };
  }

  claimTurn(input: {
    eventId: string;
    expectedVersion: number;
    fencingToken: number;
    leaseExpiresAt: Date;
    now: Date;
    turnId: string;
    workerId: string;
  }): ConversationTransition<ClaimedTurn> {
    this.assertVersion(input.expectedVersion);
    this.assertOpen();
    validateDate(input.now, 'Turn claim time');
    validateDate(input.leaseExpiresAt, 'Turn claim lease expiry');
    validateIdentifier(input.eventId, 'Event ID');
    validateIdentifier(input.workerId, 'Worker ID');
    validatePositiveSafeInteger(input.fencingToken, 'Fencing token');
    if (input.leaseExpiresAt.getTime() <= input.now.getTime()) {
      throw new ConversationInvalidTransitionError(
        'Turn claim lease must expire in the future.',
      );
    }
    if (
      this.state.turns.some(
        (turn) =>
          turn.status === 'claimed' &&
          turn.claim !== null &&
          turn.claim.leaseExpiresAt.getTime() > input.now.getTime() &&
          turn.id !== input.turnId,
      )
    ) {
      throw new ConversationInvalidTransitionError(
        'Another conversation turn is already claimed.',
      );
    }
    if (input.fencingToken <= this.state.fencingTokenHighWatermark) {
      throw new ConversationStaleFencingTokenError();
    }

    const turn = this.findTurn(input.turnId);
    const firstClaimable = [...this.state.turns]
      .filter(
        (candidate) =>
          candidate.status === 'accepted' ||
          (candidate.status === 'claimed' &&
            candidate.claim !== null &&
            candidate.claim.leaseExpiresAt.getTime() <= input.now.getTime()),
      )
      .sort((left, right) => left.receivedSequence - right.receivedSequence)[0];
    if (firstClaimable?.id !== turn.id) {
      throw new ConversationInvalidTransitionError(
        'Conversation turns must be claimed in received sequence order.',
      );
    }
    const isExpiredClaim =
      turn.status === 'claimed' &&
      turn.claim !== null &&
      turn.claim.leaseExpiresAt.getTime() <= input.now.getTime();
    if (turn.status !== 'accepted' && !isExpiredClaim) {
      throw new ConversationInvalidTransitionError(
        `Cannot claim a turn in ${turn.status} state.`,
      );
    }

    const eventSequence = this.state.lastPublicEventSequence + 1;
    const nextVersion = this.state.version + 1;
    const event: TurnProcessingPublicEvent = {
      cursor: encodePublicEventCursor(eventSequence),
      eventId: input.eventId,
      occurredAt: new Date(input.now.getTime()),
      payload: { turnId: turn.id },
      schemaVersion: 1,
      sequence: eventSequence,
      sessionId: this.state.id,
      type: 'turn.processing',
    };
    this.state = {
      ...this.state,
      fencingTokenHighWatermark: input.fencingToken,
      lastPublicEventSequence: eventSequence,
      turns: replaceTurn(this.state.turns, {
        ...turn,
        claim: {
          fencingToken: input.fencingToken,
          leaseExpiresAt: new Date(input.leaseExpiresAt.getTime()),
          workerId: input.workerId,
        },
        status: 'claimed',
      }),
      version: nextVersion,
    };

    return {
      events: [event],
      result: {
        conversationVersion: nextVersion,
        eventCursor: event.cursor,
        fencingToken: input.fencingToken,
        turnId: turn.id,
      },
      state: this.snapshot(),
    };
  }

  completeTurn(input: {
    eventId: string;
    expectedVersion: number;
    fencingToken: number;
    now: Date;
    outcome: CustomerSafeTurnOutcome;
    turnId: string;
    usage: TurnBudgetUsage;
    assistantReleaseRevision?: string;
    assistantReleaseReceipt?: ConversationReleaseCommitReceipt;
  }): ConversationTransition<CompletedTurn> {
    this.assertVersion(input.expectedVersion);
    validateDate(input.now, 'Turn completion time');
    validateIdentifier(input.eventId, 'Event ID');
    const turn = this.findTurn(input.turnId);
    this.assertCurrentClaim(turn, input.fencingToken, input.now);
    if (turn.status !== 'claimed') {
      throw new ConversationInvalidTransitionError(
        `Cannot complete a turn in ${turn.status} state.`,
      );
    }
    validateUsage(input.usage, turn.budget);
    if (
      input.assistantReleaseRevision !== undefined &&
      (input.assistantReleaseRevision.length < 1 ||
        input.assistantReleaseRevision.length > 160)
    ) {
      throw new ConversationInvalidTransitionError(
        'Assistant release revision must be non-empty and bounded.',
      );
    }
    if (
      (input.assistantReleaseRevision === undefined) !==
      (input.assistantReleaseReceipt === undefined)
    ) {
      throw new ConversationInvalidTransitionError(
        'Assistant release revision and receipt must be provided together.',
      );
    }
    const assistantReleaseReceipt =
      input.assistantReleaseReceipt === undefined
        ? turn.assistantReleaseReceipt
        : validateReleaseCommitReceipt(
            input.assistantReleaseReceipt,
            input.assistantReleaseRevision,
            input.now,
            this.state.id,
            input.turnId,
            input.expectedVersion,
            input.fencingToken,
          );

    const eventSequence = this.state.lastPublicEventSequence + 1;
    const nextVersion = this.state.version + 1;
    const event = createCompletionEvent({
      eventId: input.eventId,
      now: input.now,
      outcome: input.outcome,
      sequence: eventSequence,
      sessionId: this.state.id,
      turnId: turn.id,
    });
    const outcome =
      input.outcome.kind === 'answer'
        ? 'answered'
        : input.outcome.kind === 'clarification'
          ? 'clarification_required'
          : input.outcome.kind === 'refusal'
            ? 'refused'
            : 'handed_off';

    this.state = {
      ...this.state,
      budget: releaseUnusedBudget(this.state.budget, turn.budget, input.usage),
      lastPublicEventSequence: eventSequence,
      status: input.outcome.kind === 'handoff' ? 'handoff' : this.state.status,
      turns: replaceTurn(this.state.turns, {
        ...turn,
        assistantReleaseRevision:
          input.assistantReleaseRevision ?? turn.assistantReleaseRevision,
        assistantReleaseReceipt,
        claim: null,
        status: input.outcome.kind === 'handoff' ? 'handed_off' : 'completed',
        usage: { ...input.usage },
      }),
      version: nextVersion,
    };

    return {
      events: [event],
      result: {
        conversationVersion: nextVersion,
        eventCursor: event.cursor,
        outcome,
        turnId: turn.id,
      },
      state: this.snapshot(),
    };
  }

  cancelTurn(input: {
    authority: ConversationCancellationAuthority;
    eventId: string;
    expectedVersion: number;
    fencingToken?: number;
    now: Date;
    reason: ConversationCancellationReason;
    turnId: string;
    usage?: TurnBudgetUsage;
  }): ConversationTransition<CancelledTurn> {
    this.assertVersion(input.expectedVersion);
    validateDate(input.now, 'Turn cancellation time');
    validateIdentifier(input.eventId, 'Event ID');
    validateCancellationAuthorityReason(input.authority, input.reason);
    const turn = this.findTurn(input.turnId);
    if (turn.status !== 'accepted' && turn.status !== 'claimed') {
      throw new ConversationInvalidTransitionError(
        `Cannot cancel a turn in ${turn.status} state.`,
      );
    }
    let usage: TurnBudgetUsage;
    if (input.authority === 'worker') {
      if (turn.status !== 'claimed' || input.fencingToken === undefined) {
        throw new ConversationStaleFencingTokenError();
      }
      this.assertCurrentClaim(turn, input.fencingToken, input.now);
      if (input.usage === undefined) {
        throw new ConversationInputValidationError(
          'Worker cancellation usage is required.',
        );
      }
      usage = input.usage;
    } else if (turn.status === 'accepted') {
      usage = { costMicros: 0, modelTokens: 0 };
    } else {
      usage = {
        costMicros: turn.budget.maxCostMicros,
        modelTokens: turn.budget.maxModelTokens,
      };
    }
    validateUsage(usage, turn.budget);

    const eventSequence = this.state.lastPublicEventSequence + 1;
    const nextVersion = this.state.version + 1;
    const event: TurnCancelledPublicEvent = {
      cursor: encodePublicEventCursor(eventSequence),
      eventId: input.eventId,
      occurredAt: new Date(input.now.getTime()),
      payload: { reason: input.reason, turnId: turn.id },
      schemaVersion: 1,
      sequence: eventSequence,
      sessionId: this.state.id,
      type: 'turn.cancelled',
    };
    this.state = {
      ...this.state,
      budget: releaseUnusedBudget(this.state.budget, turn.budget, usage),
      lastPublicEventSequence: eventSequence,
      turns: replaceTurn(this.state.turns, {
        ...turn,
        cancellationAuthority: input.authority,
        cancellationReason: input.reason,
        cancelledAt: new Date(input.now.getTime()),
        claim: null,
        status: 'cancelled',
        usage: { ...usage },
      }),
      version: nextVersion,
    };

    return {
      events: [event],
      result: {
        conversationVersion: nextVersion,
        eventCursor: event.cursor,
        reason: input.reason,
        turnId: turn.id,
      },
      state: this.snapshot(),
    };
  }

  closeSession(input: {
    eventId: string;
    expectedVersion: number;
    now: Date;
  }): ConversationTransition<ClosedSession> {
    this.assertVersion(input.expectedVersion);
    validateDate(input.now, 'Session close time');
    validateIdentifier(input.eventId, 'Event ID');
    if (this.state.status === 'closed') {
      throw new ConversationInvalidTransitionError(
        'Conversation is already closed.',
      );
    }

    const eventSequence = this.state.lastPublicEventSequence + 1;
    const nextVersion = this.state.version + 1;
    const event: SessionClosedPublicEvent = {
      cursor: encodePublicEventCursor(eventSequence),
      eventId: input.eventId,
      occurredAt: new Date(input.now.getTime()),
      payload: {},
      schemaVersion: 1,
      sequence: eventSequence,
      sessionId: this.state.id,
      type: 'session.closed',
    };
    this.state = {
      ...this.state,
      lastPublicEventSequence: eventSequence,
      status: 'closed',
      version: nextVersion,
    };

    return {
      events: [event],
      result: {
        conversationVersion: nextVersion,
        eventCursor: event.cursor,
      },
      state: this.snapshot(),
    };
  }

  requestHandoff(input: {
    customerMessage: string;
    eventId: string;
    expectedVersion: number;
    handoffId: string;
    now: Date;
  }): ConversationTransition<RequestedHandoff> {
    this.assertVersion(input.expectedVersion);
    this.assertOpen();
    validateDate(input.now, 'Handoff request time');
    validateIdentifier(input.eventId, 'Event ID');
    validateIdentifier(input.handoffId, 'Handoff ID');
    const customerMessage = validateCustomerOutput(input.customerMessage);

    const eventSequence = this.state.lastPublicEventSequence + 1;
    const nextVersion = this.state.version + 1;
    const event: HandoffRequestedPublicEvent = {
      cursor: encodePublicEventCursor(eventSequence),
      eventId: input.eventId,
      occurredAt: new Date(input.now.getTime()),
      payload: {
        customerMessage,
        handoffId: input.handoffId,
        reason: 'customer_requested',
        status: 'queued',
      },
      schemaVersion: 1,
      sequence: eventSequence,
      sessionId: this.state.id,
      type: 'handoff.requested',
    };
    this.state = {
      ...this.state,
      lastPublicEventSequence: eventSequence,
      status: 'handoff',
      version: nextVersion,
    };

    return {
      events: [event],
      result: {
        conversationVersion: nextVersion,
        eventCursor: event.cursor,
        handoffId: input.handoffId,
      },
      state: this.snapshot(),
    };
  }

  private assertCurrentClaim(
    turn: ConversationTurn,
    fencingToken: number,
    now?: Date,
  ): void {
    if (
      turn.claim === null ||
      fencingToken !== turn.claim.fencingToken ||
      fencingToken < this.state.fencingTokenHighWatermark ||
      (now !== undefined &&
        turn.claim.leaseExpiresAt.getTime() <= now.getTime())
    ) {
      throw new ConversationStaleFencingTokenError();
    }
  }

  private assertOpen(): void {
    if (this.state.status !== 'open') {
      throw new ConversationInvalidTransitionError(
        `Conversation is in ${this.state.status} state.`,
      );
    }
  }

  private assertVersion(expectedVersion: number): void {
    validateNonNegativeSafeInteger(
      expectedVersion,
      'Expected conversation version',
    );
    if (expectedVersion !== this.state.version) {
      throw new ConversationVersionConflictError(
        expectedVersion,
        this.state.version,
      );
    }
  }

  private findTurn(turnId: string): ConversationTurn {
    const turn = this.state.turns.find((candidate) => candidate.id === turnId);
    if (turn === undefined) throw new ConversationTurnNotFoundError(turnId);
    return turn;
  }
}

const createCompletionEvent = (input: {
  eventId: string;
  now: Date;
  outcome: CustomerSafeTurnOutcome;
  sequence: number;
  sessionId: string;
  turnId: string;
}):
  | HandoffRequestedPublicEvent
  | TurnAnsweredPublicEvent
  | TurnClarificationPublicEvent
  | TurnRefusedPublicEvent => {
  validateDate(input.now, 'Public event time');
  const base = {
    cursor: encodePublicEventCursor(input.sequence),
    eventId: input.eventId,
    occurredAt: new Date(input.now.getTime()),
    schemaVersion: 1 as const,
    sequence: input.sequence,
    sessionId: input.sessionId,
  };
  if (input.outcome.kind === 'handoff') {
    validateIdentifier(input.outcome.handoffId, 'Handoff ID');
    const customerMessage = validateCustomerOutput(
      input.outcome.customerMessage,
    );
    return {
      ...base,
      payload: {
        customerMessage,
        handoffId: input.outcome.handoffId,
        reason: input.outcome.reason,
        status: 'queued',
        turnId: input.turnId,
      },
      type: 'handoff.requested',
    };
  }
  const message = validateCustomerOutput(input.outcome.message);
  if (input.outcome.kind === 'answer') {
    if (input.outcome.citations.length > MAX_CONVERSATION_CITATIONS) {
      throw new ConversationInvalidTransitionError(
        `A customer answer cannot contain more than ${MAX_CONVERSATION_CITATIONS} citations.`,
      );
    }
    const citations = input.outcome.citations.map(validateCitation);
    const event = {
      ...base,
      payload: {
        citations,
        message,
        outcome: 'answered',
        turnId: input.turnId,
      },
      type: 'turn.completed',
    } satisfies TurnAnsweredPublicEvent;
    validatePublicEventPayloadSize(event.payload);
    return event;
  }
  if (input.outcome.kind === 'clarification') {
    if (
      input.outcome.pendingSlots.length > 16 ||
      new Set(input.outcome.pendingSlots).size !==
        input.outcome.pendingSlots.length
    ) {
      throw new ConversationInvalidTransitionError(
        'Clarification pending slots must be unique and bounded.',
      );
    }
    return {
      ...base,
      payload: {
        message,
        outcome: 'clarification_required',
        pendingSlots: [...input.outcome.pendingSlots],
        turnId: input.turnId,
      },
      type: 'turn.completed',
    };
  }
  return {
    ...base,
    payload: {
      message,
      outcome: 'refused',
      turnId: input.turnId,
    },
    type: 'turn.completed',
  };
};

const copySnapshot = (
  snapshot: ConversationRuntimeSnapshot,
): ConversationRuntimeSnapshot => ({
  ...snapshot,
  accessScope: copyAccessScope(snapshot.accessScope),
  budget: { ...snapshot.budget },
  turns: snapshot.turns.map((turn) => ({
    ...turn,
    budget: { ...turn.budget },
    claim:
      turn.claim === null
        ? null
        : {
            ...turn.claim,
            leaseExpiresAt: new Date(turn.claim.leaseExpiresAt.getTime()),
          },
    cancelledAt:
      turn.cancelledAt === null ? null : new Date(turn.cancelledAt.getTime()),
    usage: turn.usage === null ? null : { ...turn.usage },
    assistantReleaseReceipt:
      turn.assistantReleaseReceipt === null
        ? null
        : {
            ...turn.assistantReleaseReceipt,
            expiresAt: new Date(
              turn.assistantReleaseReceipt.expiresAt.getTime(),
            ),
            issuedAt: new Date(turn.assistantReleaseReceipt.issuedAt.getTime()),
          },
  })),
});

const validateReleaseCommitReceipt = (
  receipt: ConversationReleaseCommitReceipt,
  releaseRevision: string | undefined,
  now: Date,
  sessionId: string,
  turnId: string,
  conversationVersion: number,
  fencingToken: number,
): ConversationReleaseCommitReceipt => {
  if (
    releaseRevision === undefined ||
    receipt.activationId !== releaseRevision ||
    receipt.sessionId !== sessionId ||
    receipt.turnId !== turnId ||
    receipt.conversationVersion !== conversationVersion ||
    receipt.fencingToken !== fencingToken ||
    !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(
      receipt.leaseId,
    ) ||
    !/^[a-f0-9]{64}$/.test(receipt.candidateSha256) ||
    !/^[a-f0-9]{64}$/.test(receipt.activationEnvelopeSha256) ||
    !Number.isSafeInteger(receipt.pointerRevision) ||
    receipt.pointerRevision < 1
  ) {
    throw new ConversationInvalidTransitionError(
      'Assistant release commit receipt is invalid.',
    );
  }
  validateDate(receipt.issuedAt, 'Release receipt issue time');
  validateDate(receipt.expiresAt, 'Release receipt expiry time');
  validateIdentifier(receipt.requestId, 'Release receipt request ID');
  if (
    receipt.issuedAt.getTime() > now.getTime() + 5_000 ||
    receipt.issuedAt.getTime() < now.getTime() - 30_000 ||
    receipt.expiresAt.getTime() <= now.getTime() ||
    receipt.expiresAt.getTime() <= receipt.issuedAt.getTime() ||
    receipt.expiresAt.getTime() - receipt.issuedAt.getTime() > 30_000
  ) {
    throw new ConversationInvalidTransitionError(
      'Assistant release commit receipt is stale.',
    );
  }
  return {
    ...receipt,
    expiresAt: new Date(receipt.expiresAt.getTime()),
    issuedAt: new Date(receipt.issuedAt.getTime()),
  };
};

export const copyConversationPublicEvent = (
  event: ConversationPublicEvent,
): ConversationPublicEvent => {
  validateDate(event.occurredAt, 'Stored public event time');
  if (event.type === 'turn.completed' && event.payload.outcome === 'answered') {
    event.payload.citations.forEach(validateCitation);
  }
  return structuredClone(event);
};

export const sameConversationAccessScope = (
  left: ConversationAccessScope,
  right: ConversationAccessScope,
): boolean => {
  if (left.kind !== right.kind) return false;
  if (left.kind === 'public_capability') {
    return (
      right.kind === 'public_capability' &&
      left.capabilityHash === right.capabilityHash
    );
  }
  return (
    right.kind === 'authenticated_customer' &&
    left.issuer === right.issuer &&
    left.subject === right.subject
  );
};

const replaceTurn = (
  turns: readonly ConversationTurn[],
  replacement: ConversationTurn,
): readonly ConversationTurn[] =>
  turns.map((turn) => (turn.id === replacement.id ? replacement : turn));

const releaseUnusedBudget = (
  available: ConversationBudget,
  reserved: TurnBudgetReservation,
  usage: TurnBudgetUsage,
): ConversationBudget => ({
  remainingCostMicros:
    available.remainingCostMicros + reserved.maxCostMicros - usage.costMicros,
  remainingModelTokens:
    available.remainingModelTokens +
    reserved.maxModelTokens -
    usage.modelTokens,
});

const validateMessageContent = (content: string): string => {
  const normalized = content.trim();
  const length = Array.from(normalized).length;
  if (length === 0) {
    throw new ConversationInputValidationError(
      'Conversation message must not be empty.',
    );
  }
  if (length > MAX_CONVERSATION_INPUT_CHARACTERS) {
    throw new ConversationInputValidationError(
      `Conversation message exceeds ${MAX_CONVERSATION_INPUT_CHARACTERS} characters.`,
    );
  }
  return normalized;
};

const validateCustomerOutput = (message: string): string => {
  const normalized = message.trim();
  if (
    normalized.length === 0 ||
    Array.from(normalized).length > MAX_CONVERSATION_OUTPUT_CHARACTERS
  ) {
    throw new ConversationInvalidTransitionError(
      'Customer-visible output is invalid.',
    );
  }
  return normalized;
};

const validateAccessScope = (scope: ConversationAccessScope): void => {
  if (scope.kind === 'public_capability') {
    if (!/^[a-f0-9]{64}$/.test(scope.capabilityHash)) {
      throw new ConversationInputValidationError(
        'Public capability hash must be a SHA-256 hex digest.',
      );
    }
    return;
  }
  validateSafeHttpUri(scope.issuer, 'Identity issuer');
  validateIdentifier(scope.subject, 'Authenticated subject');
};

const copyAccessScope = (
  scope: ConversationAccessScope,
): ConversationAccessScope => ({ ...scope });

const validateCitation = (
  citation: ConversationCitation,
): ConversationCitation => {
  validateIdentifier(citation.sourceId, 'Citation source ID');
  validateIdentifier(citation.revision, 'Citation revision');
  const title = citation.title.trim();
  if (
    title.length === 0 ||
    Array.from(title).length > MAX_CITATION_TITLE_CHARACTERS
  ) {
    throw new ConversationInvalidTransitionError('Citation title is invalid.');
  }
  validateDate(citation.retrievedAt, 'Citation retrieval time');
  validateSafeHttpUri(
    citation.uri,
    'Citation URI',
    MAX_CITATION_URI_CHARACTERS,
  );
  return {
    ...citation,
    retrievedAt: new Date(citation.retrievedAt.getTime()),
    title,
  };
};

const validateCancellationAuthorityReason = (
  authority: ConversationCancellationAuthority,
  reason: ConversationCancellationReason,
): void => {
  if (
    (authority === 'customer' && reason !== 'user_interrupt') ||
    (authority !== 'customer' && reason === 'user_interrupt')
  ) {
    throw new ConversationInputValidationError(
      'Cancellation authority and reason are incompatible.',
    );
  }
};

const validatePublicEventPayloadSize = (
  payload: ConversationPublicEvent['payload'],
): void => {
  if (
    Buffer.byteLength(JSON.stringify(payload), 'utf8') >
    MAX_PUBLIC_EVENT_PAYLOAD_BYTES
  ) {
    throw new ConversationInvalidTransitionError(
      'Customer-visible event payload is too large.',
    );
  }
};

const validateDate = (value: Date, name: string): void => {
  let timestamp = Number.NaN;
  try {
    timestamp = Date.prototype.getTime.call(value);
  } catch {
    // Cross-realm and driver-created values must still carry the native Date
    // internal slot. Strings and date-like objects are intentionally rejected.
  }
  if (!Number.isFinite(timestamp)) {
    throw new ConversationInputValidationError(`${name} is invalid.`);
  }
};

const validateCancellationState = (turn: ConversationTurn): void => {
  const values = [
    turn.cancellationAuthority,
    turn.cancellationReason,
    turn.cancelledAt,
  ];
  if (turn.status === 'cancelled') {
    if (values.some((value) => value === null)) {
      throw new ConversationInputValidationError(
        'Stored cancellation metadata is incomplete.',
      );
    }
    validateDate(turn.cancelledAt!, 'Stored cancellation time');
    return;
  }
  if (values.some((value) => value !== null)) {
    throw new ConversationInputValidationError(
      'Stored cancellation metadata is invalid.',
    );
  }
};

const validateSafeHttpUri = (
  value: string,
  name: string,
  maxCharacters = 2_048,
): void => {
  if (Array.from(value).length > maxCharacters) {
    throw new ConversationInputValidationError(`${name} is invalid.`);
  }
  try {
    const uri = new URL(value);
    if (
      (uri.protocol !== 'https:' && uri.protocol !== 'http:') ||
      uri.username.length > 0 ||
      uri.password.length > 0
    ) {
      throw new Error('Unsafe URI.');
    }
  } catch {
    throw new ConversationInputValidationError(`${name} is invalid.`);
  }
};

const validateReservation = (reservation: TurnBudgetReservation): void => {
  validatePositiveSafeInteger(
    reservation.maxModelTokens,
    'Reserved model tokens',
  );
  validatePositiveSafeInteger(reservation.maxCostMicros, 'Reserved cost');
  if (reservation.maxModelTokens > MAX_TURN_MODEL_TOKENS) {
    throw new ConversationBudgetValidationError(
      `Turn token reservation exceeds ${MAX_TURN_MODEL_TOKENS}.`,
    );
  }
  if (reservation.maxCostMicros > MAX_TURN_COST_MICROS) {
    throw new ConversationBudgetValidationError(
      `Turn cost reservation exceeds ${MAX_TURN_COST_MICROS}.`,
    );
  }
};

const validateUsage = (
  usage: TurnBudgetUsage,
  reservation: TurnBudgetReservation,
): void => {
  validateNonNegativeSafeInteger(usage.modelTokens, 'Used model tokens');
  validateNonNegativeSafeInteger(usage.costMicros, 'Used cost');
  if (
    usage.modelTokens > reservation.maxModelTokens ||
    usage.costMicros > reservation.maxCostMicros
  ) {
    throw new ConversationBudgetValidationError(
      'Reported usage exceeds the reserved turn budget.',
    );
  }
};

const validateIdentifier = (value: string, name: string): void => {
  if (
    value.trim().length === 0 ||
    Array.from(value).length > MAX_CITATION_IDENTIFIER_CHARACTERS
  ) {
    throw new ConversationInputValidationError(`${name} is invalid.`);
  }
};

const validateFingerprint = (value: string): void => {
  if (!/^[a-f0-9]{64}$/.test(value)) {
    throw new ConversationInputValidationError(
      'Request fingerprint must be a SHA-256 hex digest.',
    );
  }
};

const validatePositiveSafeInteger = (value: number, name: string): void => {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new ConversationBudgetValidationError(
      `${name} must be a positive safe integer.`,
    );
  }
};

const validateNonNegativeSafeInteger = (value: number, name: string): void => {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new ConversationBudgetValidationError(
      `${name} must be a non-negative safe integer.`,
    );
  }
};
