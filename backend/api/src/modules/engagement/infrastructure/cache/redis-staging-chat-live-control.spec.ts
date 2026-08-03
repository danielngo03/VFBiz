import { createHash } from 'node:crypto';
import type { RedisConnectionService } from '../../../../platform/redis/redis-connection.service';
import type {
  ActiveAssistantReleaseProjection,
  AssistantReleaseBinding,
} from '../../application/ports/active-assistant-release-projection';
import type { StagingChatLiveControlExpectation } from '../../application/ports/staging-chat-live-control';
import { RedisStagingChatLiveControl } from './redis-staging-chat-live-control';

const expectation = {
  authorityDigest: 'a'.repeat(64),
  controlId: 'staging-chat-control-20260801',
  expiresAt: new Date('2026-08-02T00:00:00.000Z'),
  generation: 7,
  notBefore: new Date('2026-08-01T00:00:00.000Z'),
  releaseEnvelopeSha256: 'c'.repeat(64),
  releasePointerRevision: 11,
} satisfies StagingChatLiveControlExpectation;

const releaseBinding = {
  activationEnvelopeSha256: expectation.releaseEnvelopeSha256,
  activationId: 'activation-staging-11',
  effectiveAt: expectation.notBefore,
  expiresAt: expectation.expiresAt,
  graphRevision: 'graph-v1',
  knowledgeRevision: 'knowledge-v1',
  manifestSha256: 'd'.repeat(64),
  pointerRevision: expectation.releasePointerRevision,
  policyRevision: 'policy-v1',
} satisfies AssistantReleaseBinding;

const resolveActiveRelease = jest.fn(() => Promise.resolve(releaseBinding));
const activeReleases = {
  resolve: resolveActiveRelease,
} as unknown as ActiveAssistantReleaseProjection;

const liveSnapshot = {
  authority_digest: expectation.authorityDigest,
  control_id_digest: createHash('sha256')
    .update(expectation.controlId, 'utf8')
    .digest('hex'),
  enabled: '1',
  expires_at_ms: String(expectation.expiresAt.getTime()),
  generation: String(expectation.generation),
  not_before_ms: String(expectation.notBefore.getTime()),
  schema_version: 'vfbiz-staging-chat-live-control/v1',
};

function redisReturning(...snapshots: Record<string, string>[]) {
  const hgetall = jest.fn<Promise<Record<string, string>>, [string]>();
  for (const snapshot of snapshots) hgetall.mockResolvedValueOnce(snapshot);
  const connection = {
    client: { hgetall },
    ensureConnected: jest.fn(() => Promise.resolve()),
  } as unknown as RedisConnectionService;
  return { connection, hgetall };
}

const validNow = () => new Date('2026-08-01T12:00:00.000Z');

describe('RedisStagingChatLiveControl', () => {
  beforeEach(() => {
    resolveActiveRelease.mockClear();
  });

  it('reads one content-free atomic snapshot on every request', async () => {
    const { connection, hgetall } = redisReturning(liveSnapshot, liveSnapshot);
    const control = new RedisStagingChatLiveControl(
      connection,
      activeReleases,
      expectation,
      validNow,
    );

    await expect(control.assertLive()).resolves.toBeUndefined();
    await expect(control.assertLive()).resolves.toBeUndefined();

    expect(hgetall).toHaveBeenCalledTimes(2);
    expect(resolveActiveRelease).toHaveBeenCalledTimes(2);
    expect(resolveActiveRelease).toHaveBeenCalledWith({
      now: validNow(),
      profile: 'authenticated_customer',
    });
    expect(hgetall).toHaveBeenCalledWith(
      `vfbiz:chat:staging-live-control:v1:${liveSnapshot.control_id_digest}`,
    );
    expect(hgetall).not.toHaveBeenCalledWith(
      expect.stringContaining(expectation.controlId),
    );
    expect(JSON.stringify(liveSnapshot)).not.toMatch(
      /customer|subject|prompt|answer|document|token/i,
    );
  });

  it('applies disable on the immediately next request without a cache', async () => {
    const { connection } = redisReturning(liveSnapshot, {
      ...liveSnapshot,
      enabled: '0',
    });
    const control = new RedisStagingChatLiveControl(
      connection,
      activeReleases,
      expectation,
      validNow,
    );

    await expect(control.assertLive()).resolves.toBeUndefined();
    await expect(control.assertLive()).rejects.toMatchObject({
      reason: 'disabled',
    });
  });

  it('does not reopen when an old enabled Redis snapshot is replayed after release revocation', async () => {
    const { connection } = redisReturning(
      liveSnapshot,
      { ...liveSnapshot, enabled: '0' },
      liveSnapshot,
    );
    let release: AssistantReleaseBinding | null = releaseBinding;
    const releases = {
      resolve: jest.fn(() => Promise.resolve(release)),
    } as unknown as ActiveAssistantReleaseProjection;
    const control = new RedisStagingChatLiveControl(
      connection,
      releases,
      expectation,
      validNow,
    );

    await expect(control.assertLive()).resolves.toBeUndefined();
    release = null;
    await expect(control.assertLive()).rejects.toMatchObject({
      reason: 'disabled',
    });
    await expect(control.assertLive()).rejects.toMatchObject({
      reason: 'release-missing',
    });
  });

  it.each([
    ['missing release', null, 'release-missing'],
    [
      'rotated release pointer',
      { ...releaseBinding, pointerRevision: 12 },
      'release-mismatched',
    ],
    [
      'rotated activation envelope',
      { ...releaseBinding, activationEnvelopeSha256: 'e'.repeat(64) },
      'release-mismatched',
    ],
  ])('fails closed for %s', async (_name, release, reason) => {
    const { connection } = redisReturning(liveSnapshot);
    const releases = {
      resolve: jest.fn(() => Promise.resolve(release)),
    } as unknown as ActiveAssistantReleaseProjection;
    const control = new RedisStagingChatLiveControl(
      connection,
      releases,
      expectation,
      validNow,
    );

    await expect(control.assertLive()).rejects.toMatchObject({ reason });
  });

  it('fails closed when the release authority is unavailable', async () => {
    const { connection } = redisReturning(liveSnapshot);
    const releases = {
      resolve: jest.fn(() => Promise.reject(new Error('database secret'))),
    } as unknown as ActiveAssistantReleaseProjection;
    const control = new RedisStagingChatLiveControl(
      connection,
      releases,
      expectation,
      validNow,
    );

    await expect(control.assertLive()).rejects.toMatchObject({
      reason: 'unavailable',
    });
  });

  it.each([
    ['generation rotation', { ...liveSnapshot, generation: '8' }],
    [
      'authority rotation',
      { ...liveSnapshot, authority_digest: 'b'.repeat(64) },
    ],
    ['missing state', {}],
    ['extra field', { ...liveSnapshot, injected: '1' }],
    ['invalid enabled state', { ...liveSnapshot, enabled: 'true' }],
  ])('fails closed for %s', async (_name, snapshot) => {
    const { connection } = redisReturning(snapshot);
    const control = new RedisStagingChatLiveControl(
      connection,
      activeReleases,
      expectation,
      validNow,
    );

    await expect(control.assertLive()).rejects.toBeInstanceOf(Error);
  });

  it('fails closed before issue and at expiry', async () => {
    const { connection, hgetall } = redisReturning(liveSnapshot);
    const beforeIssue = new RedisStagingChatLiveControl(
      connection,
      activeReleases,
      expectation,
      () => new Date('2026-07-31T23:59:59.999Z'),
    );
    await expect(beforeIssue.assertLive()).rejects.toMatchObject({
      reason: 'not-yet-valid',
    });
    expect(hgetall).not.toHaveBeenCalled();

    const atExpiry = new RedisStagingChatLiveControl(
      connection,
      activeReleases,
      expectation,
      () => expectation.expiresAt,
    );
    await expect(atExpiry.assertLive()).rejects.toMatchObject({
      reason: 'expired',
    });
  });

  it('fails closed on an in-request trusted-clock rollback inside the valid window', async () => {
    const rollbackConnection = redisReturning(liveSnapshot).connection;
    const clock = jest
      .fn<Date, []>()
      .mockReturnValueOnce(validNow())
      .mockReturnValueOnce(new Date('2026-08-01T11:59:59.999Z'));
    const rolledBack = new RedisStagingChatLiveControl(
      rollbackConnection,
      activeReleases,
      expectation,
      clock,
    );
    await expect(rolledBack.assertLive()).rejects.toMatchObject({
      reason: 'clock-rollback',
    });
  });

  it('fails closed before Redis on a trusted-clock rollback between requests', async () => {
    const { connection, hgetall } = redisReturning(liveSnapshot, liveSnapshot);
    const clock = jest
      .fn<Date, []>()
      .mockReturnValueOnce(new Date('2026-08-01T12:00:00.000Z'))
      .mockReturnValueOnce(new Date('2026-08-01T12:00:01.000Z'))
      .mockReturnValueOnce(new Date('2026-08-01T12:00:01.001Z'))
      .mockReturnValueOnce(new Date('2026-08-01T12:00:00.999Z'));
    const control = new RedisStagingChatLiveControl(
      connection,
      activeReleases,
      expectation,
      clock,
    );

    await expect(control.assertLive()).resolves.toBeUndefined();
    await expect(control.assertLive()).rejects.toMatchObject({
      reason: 'clock-rollback',
    });
    expect(hgetall).toHaveBeenCalledTimes(1);
  });

  it('fails closed when Redis is unavailable', async () => {
    const connection = {
      client: {},
      ensureConnected: jest.fn(() => Promise.reject(new Error('offline'))),
    } as unknown as RedisConnectionService;
    const control = new RedisStagingChatLiveControl(
      connection,
      activeReleases,
      expectation,
      validNow,
    );

    await expect(control.assertLive()).rejects.toMatchObject({
      reason: 'unavailable',
    });
  });

  it.each([
    { ...expectation, controlId: '../unsafe' },
    { ...expectation, authorityDigest: 'A'.repeat(64) },
    { ...expectation, releaseEnvelopeSha256: 'A'.repeat(64) },
    { ...expectation, generation: 0 },
    { ...expectation, releasePointerRevision: 0 },
    { ...expectation, expiresAt: expectation.notBefore },
    {
      ...expectation,
      expiresAt: new Date('2026-08-02T00:00:00.001Z'),
    },
  ])('rejects an invalid deployment expectation', (invalid) => {
    const { connection } = redisReturning(liveSnapshot);
    expect(
      () =>
        new RedisStagingChatLiveControl(
          connection,
          activeReleases,
          invalid,
          validNow,
        ),
    ).toThrow('live control is closed');
  });
});
