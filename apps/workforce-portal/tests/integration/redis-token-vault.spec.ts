import {createHash, randomUUID} from 'node:crypto';
import {existsSync} from 'node:fs';
import {readFile} from 'node:fs/promises';
import Redis from 'ioredis';
import {afterAll, beforeAll, describe, expect, it} from 'vitest';

function loadEnvironment(source: string): void {
  for (const line of source.split(/\r?\n/u)) {
    if (line.trim() === '' || line.trimStart().startsWith('#')) continue;
    const index = line.indexOf('=');
    if (index < 1) continue;
    process.env[line.slice(0, index)] = line.slice(index + 1);
  }
}

function redisKey(prefix: string, value: string): string {
  const digest = createHash('sha256').update(value).digest('hex');
  return `vfbiz:workforce:${prefix}:${digest}`;
}

const hasRedisEnvironment =
  existsSync('.env.local') || process.env.WORKFORCE_REDIS_URL !== undefined;

describe.runIf(hasRedisEnvironment)('Redis workforce token vault (integration)', () => {
  let redis: Redis;
  let vault: typeof import('@/platform/session/redis-token-vault');
  const subjects: string[] = [];

  beforeAll(async () => {
    if (existsSync('.env.local')) {
      loadEnvironment(await readFile('.env.local', 'utf8'));
    }
    vault = await import('@/platform/session/redis-token-vault');
    redis = new Redis(process.env.WORKFORCE_REDIS_URL as string);
  });

  afterAll(async () => {
    await Promise.all(subjects.map((subject) => vault.deleteSubjectSessions(subject)));
    await redis.quit();
  });

  it('encrypts token material and supports subject-wide session deletion', async () => {
    const subject = `integration-subject-${randomUUID()}`;
    subjects.push(subject);
    const now = new Date();
    const firstId = vault.newOpaqueSessionId();
    const secondId = vault.newOpaqueSessionId();
    for (const id of [firstId, secondId]) {
      await vault.writeSession(
        {
          authenticatedAt: now,
          deviceLabel: 'Integration browser',
          emailVerified: true,
          entitlementRevision: '1',
          expiresAt: new Date(now.getTime() + 60 * 60 * 1_000),
          id,
          lastSeenAt: now,
          mfaSatisfied: true,
          networkHint: '127.0.0.0/24',
          subject,
          userAgentSummary: 'Integration test agent',
        },
        {
          accessToken: `access-secret-${id}`,
          expiresAt: new Date(now.getTime() + 5 * 60 * 1_000),
          refreshToken: `refresh-secret-${id}`,
        },
      );
    }

    const raw = await redis.get(redisKey('session', firstId));
    expect(raw).not.toBeNull();
    expect(raw).not.toContain('access-secret');
    expect(raw).not.toContain('refresh-secret');
    expect(await vault.listSubjectSessions(subject)).toHaveLength(2);
    expect(await vault.deleteSubjectSessions(subject)).toBe(2);
    expect(await vault.listSubjectSessions(subject)).toHaveLength(0);
  });

  it('expires an idle session without touching other device activity', async () => {
    const subject = `integration-idle-${randomUUID()}`;
    subjects.push(subject);
    const id = vault.newOpaqueSessionId();
    const stale = new Date(Date.now() - 40 * 60 * 1_000);
    await vault.writeSession(
      {
        authenticatedAt: stale,
        deviceLabel: null,
        emailVerified: true,
        entitlementRevision: '1',
        expiresAt: new Date(Date.now() + 60 * 60 * 1_000),
        id,
        lastSeenAt: stale,
        mfaSatisfied: true,
        networkHint: null,
        subject,
        userAgentSummary: null,
      },
      {
        accessToken: 'idle-access-secret',
        expiresAt: new Date(Date.now() + 5 * 60 * 1_000),
        refreshToken: 'idle-refresh-secret',
      },
    );

    expect(await vault.readSession(id)).toBeNull();
    expect(await redis.exists(redisKey('session', id))).toBe(0);
    expect(await redis.exists(redisKey('session-activity', id))).toBe(0);
  });

  it('does not let an in-flight refresh resurrect a revoked session', async () => {
    const subject = `integration-refresh-fence-${randomUUID()}`;
    subjects.push(subject);
    const id = vault.newOpaqueSessionId();
    const now = new Date();
    const session = {
      authenticatedAt: now,
      deviceLabel: null,
      emailVerified: true,
      entitlementRevision: '1',
      expiresAt: new Date(now.getTime() + 60 * 60 * 1_000),
      id,
      lastSeenAt: now,
      mfaSatisfied: true,
      networkHint: null,
      subject,
      userAgentSummary: null,
    };
    await vault.writeSession(session, {
      accessToken: 'old-access',
      expiresAt: new Date(now.getTime() + 60_000),
      refreshToken: 'old-refresh',
    });

    await vault.deleteSession(id);

    await expect(
      vault.writeSession(
        session,
        {
          accessToken: 'new-access',
          expiresAt: new Date(now.getTime() + 5 * 60_000),
          refreshToken: 'new-refresh',
        },
        {requireExisting: true},
      ),
    ).rejects.toThrow('revoked');
    expect(await vault.readSession(id)).toBeNull();
  });
});
