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

export abstract class ConversationRuntimeRepository {
  abstract commit(
    transition: ConversationRuntimeCommit,
  ): Promise<ConversationRuntimeCommitResult>;

  abstract findAcceptedMessage(
    sessionId: string,
    accessScope: ConversationAccessScope,
    clientMessageId: string,
  ): Promise<AcceptedMessageReplay | null>;

  abstract getSnapshot(
    sessionId: string,
    accessScope: ConversationAccessScope,
  ): Promise<ConversationRuntimeSnapshot | null>;

  abstract listPublicEvents(
    sessionId: string,
    accessScope: ConversationAccessScope,
    afterSequence: number | null,
    limit: number,
  ): Promise<readonly ConversationPublicEvent[]>;
}

export interface ConversationTurnDispatchEnvelope {
  readonly budget: {
    readonly maxCostMicros: number;
    readonly maxModelTokens: number;
  };
  readonly cancellationId: string;
  readonly content: string;
  readonly fencingToken: number;
  readonly sessionId: string;
  readonly turnId: string;
}

/**
 * VFBIZ-0017 only defines this seam. A fake/disabled implementation is used
 * until the private API–AI protocol is introduced by its own work item.
 */
export abstract class ConversationTurnDispatchPort {
  abstract dispatch(
    envelope: ConversationTurnDispatchEnvelope,
  ): Promise<{ readonly status: 'accepted' | 'disabled' }>;
}

export class DisabledConversationTurnDispatchPort extends ConversationTurnDispatchPort {
  dispatch(
    envelope: ConversationTurnDispatchEnvelope,
  ): Promise<{ readonly status: 'disabled' }> {
    void envelope;
    return Promise.resolve({ status: 'disabled' });
  }
}

export abstract class ConversationRuntimeClock {
  abstract now(): Date;
}

export abstract class ConversationRuntimeIdGenerator {
  abstract nextId(purpose: 'event' | 'handoff' | 'turn'): string;
}
