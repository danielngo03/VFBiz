import type { RedisConnectionService } from './redis-connection.service';
import { RedisThrottlerStorageService } from './redis-throttler-storage.service';

describe('RedisThrottlerStorageService', () => {
  it('maps the atomic Redis result to the Nest throttler contract', async () => {
    const evaluate = jest.fn(() => Promise.resolve([3, 59_001, 0]));
    const connection = {
      client: { eval: evaluate },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const storage = new RedisThrottlerStorageService(connection);

    await expect(
      storage.increment('client-hash', 60_000, 5, 60_000, 'default'),
    ).resolves.toEqual({
      isBlocked: false,
      timeToBlockExpire: 0,
      timeToExpire: 60,
      totalHits: 3,
    });
    expect(evaluate).toHaveBeenCalledWith(
      expect.stringContaining("redis.call('INCR'"),
      1,
      'vfbiz:throttle:default:client-hash',
      '60000',
      '5',
      '60000',
    );
  });

  it('reports a distributed block with its remaining duration', async () => {
    const connection = {
      client: { eval: jest.fn(() => Promise.resolve([6, 60_000, 1])) },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;
    const storage = new RedisThrottlerStorageService(connection);

    await expect(
      storage.increment('client-hash', 60_000, 5, 60_000, 'default'),
    ).resolves.toMatchObject({
      isBlocked: true,
      timeToBlockExpire: 60,
      totalHits: 6,
    });
  });

  it('propagates Redis outages instead of allowing unlimited traffic', async () => {
    const connection = {
      client: {},
      ensureConnected: jest.fn(() => Promise.reject(new Error('offline'))),
    } as unknown as RedisConnectionService;
    const storage = new RedisThrottlerStorageService(connection);

    await expect(
      storage.increment('client-hash', 60_000, 5, 60_000, 'default'),
    ).rejects.toThrow('offline');
  });
});
