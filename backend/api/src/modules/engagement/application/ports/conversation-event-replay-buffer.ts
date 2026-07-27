import type { ConversationPublicEvent } from '../../domain/runtime/conversation-runtime';

/**
 * Short-lived mobile reconnect acceleration only.
 * PostgreSQL remains the durable event authority.
 */
export abstract class ConversationEventReplayBuffer {
  abstract append(
    sessionId: string,
    events: readonly ConversationPublicEvent[],
  ): Promise<void>;

  /**
   * Returns null on cache miss/unavailability so callers fall back to the
   * durable event log. An empty array means the cursor is covered but current.
   */
  abstract readAfter(
    sessionId: string,
    afterCursor: string,
  ): Promise<readonly ConversationPublicEvent[] | null>;
}
