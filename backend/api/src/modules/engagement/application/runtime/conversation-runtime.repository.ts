import type {
  AcceptedMessage,
  ConversationAccessScope,
  ConversationPublicEvent,
  ConversationRuntimeSnapshot,
} from '../../domain/runtime/conversation-runtime';

export interface AcceptedMessageReplay {
  readonly accessScope: ConversationAccessScope;
  readonly requestFingerprint: string;
  readonly result: AcceptedMessage;
}

export interface ConversationRuntimeCommit {
  readonly accessScope: ConversationAccessScope;
  readonly acceptedMessageReplay?: AcceptedMessageReplay;
  readonly events: readonly ConversationPublicEvent[];
  readonly expectedVersion: number;
  readonly nextState: ConversationRuntimeSnapshot;
  readonly now: Date;
  readonly sessionId: string;
}

export type ConversationRuntimeCommitResult =
  | { readonly outcome: 'committed' }
  | {
      readonly actualVersion: number;
      readonly outcome: 'version-conflict';
    }
  | {
      readonly outcome: 'message-replay';
      readonly replay: AcceptedMessageReplay;
    };

export type ConversationPublicEventReadResult =
  | {
      readonly events: readonly ConversationPublicEvent[];
      readonly outcome: 'events';
    }
  | {
      readonly outcome: 'not-found';
    }
  | {
      readonly earliestAvailableCursor: string | null;
      readonly latestAvailableCursor: string | null;
      readonly outcome: 'resync-required';
      readonly reason:
        'cursor_expired' | 'cursor_out_of_range' | 'retention_expired';
      readonly retentionUntil: Date;
    };

export abstract class ConversationRuntimeRepository {
  abstract claimCancellationDispatches(
    now: Date,
    leaseUntil: Date,
    limit: number,
  ): Promise<readonly ConversationCancellationDispatch[]>;

  abstract completeCancellationDispatch(dispatchId: string): Promise<void>;
  abstract commit(
    transition: ConversationRuntimeCommit,
  ): Promise<ConversationRuntimeCommitResult>;

  abstract findAcceptedMessage(
    sessionId: string,
    accessScope: ConversationAccessScope,
    clientMessageId: string,
    now: Date,
  ): Promise<AcceptedMessageReplay | null>;

  abstract findDispatchCandidates(
    now: Date,
    limit: number,
  ): Promise<readonly ConversationDispatchCandidate[]>;

  abstract getSnapshot(
    sessionId: string,
    accessScope: ConversationAccessScope,
    now: Date,
  ): Promise<ConversationRuntimeSnapshot | null>;

  abstract getTurnExecutionContext(
    sessionId: string,
    accessScope: ConversationAccessScope,
    turnId: string,
    now: Date,
  ): Promise<ConversationTurnExecutionContext | null>;

  abstract listPublicEvents(
    sessionId: string,
    accessScope: ConversationAccessScope,
    afterSequence: number | null,
    limit: number,
    now: Date,
  ): Promise<ConversationPublicEventReadResult>;

  abstract purgeCustomerSubject(
    deletionRequestId: string,
    issuer: string,
    subject: string,
  ): Promise<number>;

  abstract purgeExpiredSessions(now: Date, limit: number): Promise<number>;

  abstract retryCancellationDispatch(
    dispatchId: string,
    availableAt: Date,
    terminal: boolean,
  ): Promise<void>;

  abstract recordTurnDispatchFailure(input: {
    correlationId: string;
    failureCode: string;
    fencingToken: number;
    nextAttemptAt: Date;
    sessionId: string;
    terminal: boolean;
    turnId: string;
  }): Promise<boolean>;
}

export interface ConversationCancellationDispatch {
  readonly accessScope: ConversationAccessScope;
  readonly assistantProfile: 'authenticated_customer' | 'public_customer';
  readonly attempts: number;
  readonly budget: {
    readonly maxCostMicros: number;
    readonly maxModelTokens: number;
  };
  readonly conversationVersion: number;
  readonly correlationId: string;
  readonly dispatchId: string;
  readonly fencingToken: number;
  readonly locale: 'en' | 'vi';
  readonly release: ConversationTurnExecutionContext['release'];
  readonly policyRevision: string;
  readonly reason:
    'budget_exhausted' | 'system_shutdown' | 'timeout' | 'user_interrupt';
  readonly requestId: string;
  readonly sessionId: string;
  readonly turnId: string;
}

export interface ConversationDispatchCandidate {
  readonly accessScope: ConversationAccessScope;
  readonly attempts: number;
  readonly expectedVersion: number;
  readonly nextFencingToken: number;
  readonly sessionId: string;
  readonly turnId: string;
}

export interface ConversationTurnExecutionContext {
  readonly accessScope: ConversationAccessScope;
  readonly assistantProfile: 'authenticated_customer' | 'public_customer';
  readonly budget: {
    readonly maxCostMicros: number;
    readonly maxModelTokens: number;
  };
  readonly content: string;
  readonly conversationVersion: number;
  readonly fencingToken: number;
  readonly locale: 'en' | 'vi';
  readonly release: {
    readonly activationEnvelopeSha256: string;
    readonly activationId: string;
    readonly effectiveAt: Date;
    readonly expiresAt: Date;
    readonly graphRevision: string;
    readonly knowledgeRevision: string;
    readonly manifestSha256: string;
    readonly pointerRevision: number;
    readonly policyRevision: string;
  };
  readonly policyRevision: string;
  readonly sessionId: string;
  readonly turnId: string;
}

export abstract class ConversationRuntimeClock {
  abstract now(): Date;
}

export abstract class ConversationRuntimeIdGenerator {
  abstract nextId(purpose: 'event' | 'handoff' | 'turn'): string;
}
