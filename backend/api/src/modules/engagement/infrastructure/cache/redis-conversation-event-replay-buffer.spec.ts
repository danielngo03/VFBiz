import { RedisConversationEventReplayBuffer } from './redis-conversation-event-replay-buffer';
import type { RedisConnectionService } from '../../../../platform/redis/redis-connection.service';
import type { ConversationPublicEvent } from '../../domain/runtime/conversation-runtime';

function event(sequence: number): ConversationPublicEvent {
  return {
    cursor: `event-v1:${sequence}`,
    eventId: `event-${sequence}`,
    occurredAt: new Date('2026-07-27T00:00:00.000Z'),
    payload: { turnId: 'turn-1' },
    schemaVersion: 1,
    sequence,
    sessionId: '00000000-0000-4000-8000-000000000001',
    type: 'turn.processing',
  };
}

describe('RedisConversationEventReplayBuffer', () => {
  it('keeps at most 50 events for five minutes', async () => {
    const transaction = {
      exec: jest.fn(() => Promise.resolve([])),
      expire: jest.fn().mockReturnThis(),
      zadd: jest.fn().mockReturnThis(),
      zremrangebyrank: jest.fn().mockReturnThis(),
    };
    const connection = {
      client: { multi: jest.fn(() => transaction) },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const buffer = new RedisConversationEventReplayBuffer(connection);

    await buffer.append(event(1).sessionId, [event(1), event(2)]);

    expect(transaction.zadd).toHaveBeenCalledTimes(2);
    expect(transaction.zremrangebyrank).toHaveBeenCalledWith(
      expect.any(String),
      0,
      -51,
    );
    expect(transaction.expire).toHaveBeenCalledWith(expect.any(String), 300);
    expect(transaction.exec).toHaveBeenCalledTimes(1);
  });

  it('replays a covered cursor in sequence order', async () => {
    const connection = {
      client: {
        zrange: jest.fn(() => Promise.resolve([JSON.stringify(event(6)), '6'])),
        zrangebyscore: jest.fn(() =>
          Promise.resolve([
            JSON.stringify({
              ...event(6),
              occurredAt: event(6).occurredAt.toISOString(),
            }),
          ]),
        ),
      },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const buffer = new RedisConversationEventReplayBuffer(connection);

    const replay = await buffer.readAfter(event(6).sessionId, 'event-v1:5');

    expect(replay?.map((item) => item.cursor)).toEqual(['event-v1:6']);
    expect(replay?.[0]?.occurredAt).toBeInstanceOf(Date);
  });

  it('returns a cache miss when the requested cursor is older than the buffer', async () => {
    const zrangebyscore = jest.fn();
    const connection = {
      client: {
        zrange: jest.fn(() =>
          Promise.resolve([JSON.stringify(event(50)), '50']),
        ),
        zrangebyscore,
      },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const buffer = new RedisConversationEventReplayBuffer(connection);

    await expect(
      buffer.readAfter(event(50).sessionId, 'event-v1:1'),
    ).resolves.toBeNull();
    expect(zrangebyscore).not.toHaveBeenCalled();
  });

  it('falls back when cached events are not contiguous or belong to another session', async () => {
    const other = {
      ...event(7),
      sessionId: '00000000-0000-4000-8000-000000000002',
    };
    const connection = {
      client: {
        zrange: jest.fn(() => Promise.resolve([JSON.stringify(event(6)), '6'])),
        zrangebyscore: jest.fn(() =>
          Promise.resolve([
            JSON.stringify({
              ...event(8),
              occurredAt: event(8).occurredAt.toISOString(),
            }),
            JSON.stringify({
              ...other,
              occurredAt: other.occurredAt.toISOString(),
            }),
          ]),
        ),
      },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const buffer = new RedisConversationEventReplayBuffer(connection);

    await expect(
      buffer.readAfter(event(6).sessionId, 'event-v1:5'),
    ).resolves.toBeNull();
  });

  it('fails open to the durable event log when Redis is unavailable', async () => {
    const connection = {
      client: {},
      ensureConnected: jest.fn(() => Promise.reject(new Error('offline'))),
    } as unknown as RedisConnectionService;
    const buffer = new RedisConversationEventReplayBuffer(connection);

    await expect(
      buffer.readAfter(event(1).sessionId, 'event-v1:1'),
    ).resolves.toBeNull();
    await expect(
      buffer.append(event(1).sessionId, [event(1)]),
    ).resolves.toBeUndefined();
  });
});
