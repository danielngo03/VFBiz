import { Injectable, Logger } from '@nestjs/common';
import { RedisConnectionService } from '../../../../platform/redis/redis-connection.service';
import { ConversationEventReplayBuffer } from '../../application/ports/conversation-event-replay-buffer';
import type { ConversationPublicEvent } from '../../domain/runtime/conversation-runtime';

const REPLAY_TTL_SECONDS = 5 * 60;
const REPLAY_EVENT_LIMIT = 50;
const CURSOR_PATTERN = /^event-v1:(\d+)$/;

@Injectable()
export class RedisConversationEventReplayBuffer extends ConversationEventReplayBuffer {
  private readonly logger = new Logger(RedisConversationEventReplayBuffer.name);

  constructor(private readonly redis: RedisConnectionService) {
    super();
  }

  async append(
    sessionId: string,
    events: readonly ConversationPublicEvent[],
  ): Promise<void> {
    if (events.length === 0) return;
    try {
      await this.redis.ensureConnected();
      const key = replayKey(sessionId);
      const transaction = this.redis.client.multi();
      for (const event of events) {
        transaction.zadd(key, event.sequence, serializeEvent(event));
      }
      transaction.zremrangebyrank(key, 0, -(REPLAY_EVENT_LIMIT + 1));
      transaction.expire(key, REPLAY_TTL_SECONDS);
      await transaction.exec();
    } catch (error) {
      this.logger.warn({
        error: error instanceof Error ? error.message : String(error),
        message:
          'Conversation replay cache append failed; durable replay remains available.',
        sessionId,
      });
    }
  }

  async readAfter(
    sessionId: string,
    afterCursor: string,
  ): Promise<readonly ConversationPublicEvent[] | null> {
    const afterSequence = parseCursor(afterCursor);
    if (afterSequence === null) return null;
    try {
      await this.redis.ensureConnected();
      const key = replayKey(sessionId);
      const oldest = await this.redis.client.zrange(key, 0, 0, 'WITHSCORES');
      if (oldest.length !== 2) return null;
      const oldestSequence = Number(oldest[1]);
      if (
        !Number.isSafeInteger(oldestSequence) ||
        afterSequence < oldestSequence - 1
      ) {
        return null;
      }
      const entries = await this.redis.client.zrangebyscore(
        key,
        `(${afterSequence}`,
        '+inf',
        'LIMIT',
        0,
        REPLAY_EVENT_LIMIT,
      );
      return entries.map(deserializeEvent);
    } catch (error) {
      this.logger.warn({
        error: error instanceof Error ? error.message : String(error),
        message:
          'Conversation replay cache read failed; falling back to PostgreSQL.',
        sessionId,
      });
      return null;
    }
  }
}

function replayKey(sessionId: string): string {
  return `vfbiz:conversation:${sessionId}:replay:v1`;
}

function parseCursor(cursor: string): number | null {
  const match = CURSOR_PATTERN.exec(cursor);
  if (match === null) return null;
  const sequence = Number(match[1]);
  return Number.isSafeInteger(sequence) && sequence >= 0 ? sequence : null;
}

function serializeEvent(event: ConversationPublicEvent): string {
  return JSON.stringify({
    ...event,
    occurredAt: event.occurredAt.toISOString(),
  });
}

function deserializeEvent(value: string): ConversationPublicEvent {
  const event = JSON.parse(value) as Omit<
    ConversationPublicEvent,
    'occurredAt'
  > & {
    occurredAt: string;
  };
  return {
    ...event,
    occurredAt: new Date(event.occurredAt),
  } as ConversationPublicEvent;
}
