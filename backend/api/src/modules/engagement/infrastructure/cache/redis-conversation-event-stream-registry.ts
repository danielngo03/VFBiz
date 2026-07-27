import { Injectable, Logger } from '@nestjs/common';
import { RedisConnectionService } from '../../../../platform/redis/redis-connection.service';
import {
  ConversationEventStreamRegistry,
  type ConversationEventStreamLease,
} from '../../application/ports/conversation-event-stream-registry';

const ACQUIRE_STREAM_SCRIPT = `
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[3]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[4])
redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[5]))
return 1
`;

@Injectable()
export class RedisConversationEventStreamRegistry extends ConversationEventStreamRegistry {
  private readonly logger = new Logger(
    RedisConversationEventStreamRegistry.name,
  );

  constructor(private readonly redis: RedisConnectionService) {
    super();
  }

  async acquire(input: {
    connectionId: string;
    expiresAt: Date;
    maximumConnections: number;
    now: Date;
    sessionId: string;
  }): Promise<ConversationEventStreamLease | null> {
    if (
      input.expiresAt.getTime() <= input.now.getTime() ||
      !Number.isSafeInteger(input.maximumConnections) ||
      input.maximumConnections < 1
    ) {
      throw new Error('Invalid conversation event stream lease policy.');
    }
    try {
      await this.redis.ensureConnected();
      const leaseDurationMs = input.expiresAt.getTime() - input.now.getTime();
      const result = await this.redis.client.eval(
        ACQUIRE_STREAM_SCRIPT,
        1,
        streamKey(input.sessionId),
        String(input.now.getTime()),
        String(input.expiresAt.getTime()),
        String(input.maximumConnections),
        input.connectionId,
        String(leaseDurationMs + 30_000),
      );
      if (result !== 1) return null;
      return {
        connectionId: input.connectionId,
        expiresAt: input.expiresAt,
        sessionId: input.sessionId,
      };
    } catch (error) {
      // Admission control fails closed. Durable event reads remain available
      // through the non-streaming message/session endpoints.
      this.logger.error({
        error: error instanceof Error ? error.message : String(error),
        message: 'Conversation event stream admission is unavailable.',
        sessionId: input.sessionId,
      });
      return null;
    }
  }

  async release(lease: ConversationEventStreamLease): Promise<void> {
    try {
      await this.redis.ensureConnected();
      await this.redis.client.zrem(
        streamKey(lease.sessionId),
        lease.connectionId,
      );
    } catch (error) {
      // The sorted-set score expires the lease even if explicit cleanup fails.
      this.logger.warn({
        error: error instanceof Error ? error.message : String(error),
        message: 'Conversation event stream lease cleanup was deferred.',
        sessionId: lease.sessionId,
      });
    }
  }
}

function streamKey(sessionId: string): string {
  return `vfbiz:conversation:${sessionId}:sse-connections:v1`;
}
