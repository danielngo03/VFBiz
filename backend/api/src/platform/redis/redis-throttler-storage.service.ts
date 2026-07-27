import { Injectable } from '@nestjs/common';
import type { ThrottlerStorage } from '@nestjs/throttler';
import { RedisConnectionService } from './redis-connection.service';

const INCREMENT_SCRIPT = `
local total = redis.call('INCR', KEYS[1])
if total == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
local blocked = 0
if total > tonumber(ARGV[2]) then
  blocked = 1
  if tonumber(ARGV[3]) > ttl then
    redis.call('PEXPIRE', KEYS[1], ARGV[3])
    ttl = tonumber(ARGV[3])
  end
end
return {total, ttl, blocked}
`;

/**
 * Multi-instance throttling storage. Redis failure is deliberately propagated:
 * an abuse-control outage must not silently turn into unlimited public traffic.
 */
@Injectable()
export class RedisThrottlerStorageService implements ThrottlerStorage {
  constructor(private readonly redis: RedisConnectionService) {}

  async increment(
    key: string,
    ttl: number,
    limit: number,
    blockDuration: number,
    throttlerName: string,
  ): Promise<{
    isBlocked: boolean;
    timeToBlockExpire: number;
    timeToExpire: number;
    totalHits: number;
  }> {
    await this.redis.ensureConnected();
    const storageKey = `vfbiz:throttle:${throttlerName}:${key}`;
    const result = await this.redis.client.eval(
      INCREMENT_SCRIPT,
      1,
      storageKey,
      String(ttl),
      String(limit),
      String(blockDuration),
    );
    if (
      !Array.isArray(result) ||
      result.length !== 3 ||
      result.some((value) => typeof value !== 'number')
    ) {
      throw new Error('Redis returned an invalid throttling record.');
    }
    const [totalHits, ttlMilliseconds, blocked] = result as [
      number,
      number,
      number,
    ];
    return {
      isBlocked: blocked === 1,
      timeToBlockExpire:
        blocked === 1 ? Math.max(0, Math.ceil(ttlMilliseconds / 1_000)) : 0,
      timeToExpire: Math.max(0, Math.ceil(ttlMilliseconds / 1_000)),
      totalHits,
    };
  }
}
