export const MAX_CONVERSATION_INPUT_CHARACTERS = 12_000;
export const MAX_TURN_MODEL_TOKENS = 32_000;
export const MAX_TURN_COST_MICROS = 10_000_000;

export type ConversationCancellationReason =
  'budget_exhausted' | 'system_shutdown' | 'timeout' | 'user_interrupt';

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

export interface ConversationTurn {
  readonly budget: TurnBudgetReservation;
  readonly claim: ConversationTurnClaim | null;
  readonly clientMessageId: string;
  readonly content: string;
  readonly id: string;
  readonly receivedSequence: number;
  readonly requestFingerprint: string;
  readonly status:
    'accepted' | 'cancelled' | 'claimed' | 'completed' | 'handed_off';
}

export interface ConversationRuntimeSnapshot {
  readonly accessScope: ConversationAccessScope;
  readonly budget: ConversationBudget;
  readonly fencingTokenHighWatermark: number;
  readonly id: string;
  readonly lastPublicEventSequence: number;
  readonly lastReceivedSequence: number;
  readonly status: 'handoff' | 'open';
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
    readonly turnId: string;
  };
  readonly type: 'handoff.requested';
}

/**
 * This union is the only event shape exposed to customer transports.
 * It deliberately has no prompt, hidden reasoning, raw tool result or
 * provider response field.
 */
export type ConversationPublicEvent =
  | HandoffRequestedPublicEvent
  | MessageAcceptedPublicEvent
  | TurnAnsweredPublicEvent
  | TurnCancelledPublicEvent
  | TurnProcessingPublicEvent
  | TurnRefusedPublicEvent;

export type CustomerSafeTurnOutcome =
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
  readonly outcome: 'answered' | 'handed_off' | 'refused';
  readonly turnId: string;
}

export interface CancelledTurn {
  readonly conversationVersion: number;
  readonly eventCursor: string;
  readonly reason: ConversationCancellationReason;
  readonly turnId: string;
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
    snapshot.turns.forEach((turn) => {
      if (turn.claim !== null) {
        validateDate(turn.claim.leaseExpiresAt, 'Stored turn lease expiry');
      }
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
      budget: { ...input.budget },
      claim: null,
      clientMessageId: input.clientMessageId,
      content,
      id: input.turnId,
      receivedSequence,
      requestFingerprint: input.requestFingerprint,
      status: 'accepted',
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
        status: input.outcome.kind === 'handoff' ? 'handed_off' : 'completed',
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
    const turn = this.findTurn(input.turnId);
    if (turn.status === 'claimed') {
      if (input.fencingToken === undefined) {
        throw new ConversationStaleFencingTokenError();
      }
      this.assertCurrentClaim(turn, input.fencingToken, input.now);
    } else if (turn.status !== 'accepted') {
      if (
        turn.claim !== null &&
        input.fencingToken !== undefined &&
        input.fencingToken !== turn.claim.fencingToken
      ) {
        throw new ConversationStaleFencingTokenError();
      }
      throw new ConversationInvalidTransitionError(
        `Cannot cancel a turn in ${turn.status} state.`,
      );
    }
    const usage = input.usage ?? { costMicros: 0, modelTokens: 0 };
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
        status: 'cancelled',
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
    const citations = input.outcome.citations.map(validateCitation);
    return {
      ...base,
      payload: {
        citations,
        message,
        outcome: 'answered',
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
  })),
});

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
  if (normalized.length === 0) {
    throw new ConversationInvalidTransitionError(
      'Customer-visible output must not be empty.',
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
  if (title.length === 0 || title.length > 300) {
    throw new ConversationInvalidTransitionError('Citation title is invalid.');
  }
  validateDate(citation.retrievedAt, 'Citation retrieval time');
  validateSafeHttpUri(citation.uri, 'Citation URI');
  return {
    ...citation,
    retrievedAt: new Date(citation.retrievedAt.getTime()),
    title,
  };
};

const validateDate = (value: Date, name: string): void => {
  if (!(value instanceof Date) || !Number.isFinite(value.getTime())) {
    throw new ConversationInputValidationError(`${name} is invalid.`);
  }
};

const validateSafeHttpUri = (value: string, name: string): void => {
  if (value.length > 2_048) {
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
  if (value.trim().length === 0 || value.length > 160) {
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
