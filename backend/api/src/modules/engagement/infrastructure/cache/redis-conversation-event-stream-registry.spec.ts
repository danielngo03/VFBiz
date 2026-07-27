import type { RedisConnectionService } from '../../../../platform/redis/redis-connection.service';
import { RedisConversationEventStreamRegistry } from './redis-conversation-event-stream-registry';

const input = {
  connectionId: '00000000-0000-4000-8000-000000000011',
  expiresAt: new Date('2026-07-27T00:05:00.000Z'),
  maximumConnections: 3,
  now: new Date('2026-07-27T00:00:00.000Z'),
  sessionId: '00000000-0000-4000-8000-000000000001',
};

describe('RedisConversationEventStreamRegistry', () => {
  it('atomically acquires a five-minute cross-instance stream lease', async () => {
    const evaluate = jest.fn(() => Promise.resolve(1));
    const connection = {
      client: {
        eval: evaluate,
      },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const registry = new RedisConversationEventStreamRegistry(connection);

    await expect(registry.acquire(input)).resolves.toEqual({
      connectionId: input.connectionId,
      expiresAt: input.expiresAt,
      sessionId: input.sessionId,
    });
    expect(evaluate).toHaveBeenCalledWith(
      expect.stringContaining('ZREMRANGEBYSCORE'),
      1,
      expect.stringContaining(input.sessionId),
      String(input.now.getTime()),
      String(input.expiresAt.getTime()),
      '3',
      input.connectionId,
      '330000',
    );
  });

  it('rejects a stream when the per-session quota is full', async () => {
    const connection = {
      client: {
        eval: jest.fn(() => Promise.resolve(0)),
      },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const registry = new RedisConversationEventStreamRegistry(connection);

    await expect(registry.acquire(input)).resolves.toBeNull();
  });

  it('fails closed when Redis admission control is unavailable', async () => {
    const connection = {
      client: {},
      ensureConnected: jest.fn(() => Promise.reject(new Error('offline'))),
    } as unknown as RedisConnectionService;
    const registry = new RedisConversationEventStreamRegistry(connection);

    await expect(registry.acquire(input)).resolves.toBeNull();
  });

  it('releases the exact connection without affecting sibling streams', async () => {
    const remove = jest.fn(() => Promise.resolve(1));
    const connection = {
      client: {
        zrem: remove,
      },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const registry = new RedisConversationEventStreamRegistry(connection);

    await registry.release({
      connectionId: input.connectionId,
      expiresAt: input.expiresAt,
      sessionId: input.sessionId,
    });

    expect(remove).toHaveBeenCalledWith(
      expect.stringContaining(input.sessionId),
      input.connectionId,
    );
  });
});
