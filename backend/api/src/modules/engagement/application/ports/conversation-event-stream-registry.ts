export interface ConversationEventStreamLease {
  readonly connectionId: string;
  readonly expiresAt: Date;
  readonly sessionId: string;
}

/**
 * Cross-instance admission control for long-lived SSE connections.
 *
 * Redis is coordination only: losing this lease closes or rejects a stream,
 * but never loses conversation events because PostgreSQL remains authoritative.
 */
export abstract class ConversationEventStreamRegistry {
  abstract acquire(input: {
    connectionId: string;
    expiresAt: Date;
    maximumConnections: number;
    now: Date;
    sessionId: string;
  }): Promise<ConversationEventStreamLease | null>;

  abstract release(lease: ConversationEventStreamLease): Promise<void>;
}
