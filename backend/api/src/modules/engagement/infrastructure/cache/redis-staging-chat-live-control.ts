import { createHash } from 'node:crypto';
import { RedisConnectionService } from '../../../../platform/redis/redis-connection.service';
import {
  ActiveAssistantReleaseProjection,
  type AssistantReleaseBinding,
} from '../../application/ports/active-assistant-release-projection';
import {
  StagingChatLiveControl,
  StagingChatLiveControlClosedError,
  type StagingChatLiveControlExpectation,
} from '../../application/ports/staging-chat-live-control';

const CONTROL_SCHEMA = 'vfbiz-staging-chat-live-control/v1';
const MAXIMUM_VALIDITY_WINDOW_MS = 24 * 60 * 60 * 1_000;
const SHA256 = /^[a-f0-9]{64}$/;
const CONTROL_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;

type TrustedClock = () => Date;

interface ControlSnapshot {
  readonly authority_digest: string;
  readonly control_id_digest: string;
  readonly enabled: string;
  readonly expires_at_ms: string;
  readonly generation: string;
  readonly not_before_ms: string;
  readonly schema_version: string;
}

const SNAPSHOT_KEYS = [
  'authority_digest',
  'control_id_digest',
  'enabled',
  'expires_at_ms',
  'generation',
  'not_before_ms',
  'schema_version',
] as const;

/**
 * Reads one exact, content-free Redis hash on every request. The expectation is
 * deployment-owned configuration; Redis can disable it but cannot mint a new
 * deployment identity, generation or authority digest.
 */
export class RedisStagingChatLiveControl extends StagingChatLiveControl {
  private readonly expected: ControlSnapshot;
  private readonly expectedReleaseEnvelopeSha256: string;
  private readonly expectedReleasePointerRevision: number;
  private readonly key: string;
  private lastTrustedTimeMs: number | null = null;

  constructor(
    private readonly redis: RedisConnectionService,
    private readonly releases: ActiveAssistantReleaseProjection,
    expectation: StagingChatLiveControlExpectation,
    private readonly clock: TrustedClock = () => new Date(),
  ) {
    super();
    validateExpectation(expectation);
    this.expectedReleaseEnvelopeSha256 = expectation.releaseEnvelopeSha256;
    this.expectedReleasePointerRevision = expectation.releasePointerRevision;
    const controlIdDigest = sha256(expectation.controlId);
    this.key = `vfbiz:chat:staging-live-control:v1:${controlIdDigest}`;
    this.expected = {
      authority_digest: expectation.authorityDigest,
      control_id_digest: controlIdDigest,
      enabled: '1',
      expires_at_ms: String(expectation.expiresAt.getTime()),
      generation: String(expectation.generation),
      not_before_ms: String(expectation.notBefore.getTime()),
      schema_version: CONTROL_SCHEMA,
    };
  }

  async assertLive(): Promise<void> {
    this.assertWindow(this.clock());
    let observed: Record<string, string>;
    try {
      await this.redis.ensureConnected();
      observed = await this.redis.client.hgetall(this.key);
    } catch {
      throw new StagingChatLiveControlClosedError('unavailable');
    }
    const releaseCheckAt = this.clock();
    this.assertWindow(releaseCheckAt);
    this.assertSnapshot(observed);
    let release: AssistantReleaseBinding | null;
    try {
      release = await this.releases.resolve({
        now: releaseCheckAt,
        profile: 'authenticated_customer',
      });
    } catch {
      throw new StagingChatLiveControlClosedError('unavailable');
    }
    this.assertWindow(this.clock());
    this.assertRelease(release);
  }

  private assertRelease(release: AssistantReleaseBinding | null): void {
    if (release === null) {
      throw new StagingChatLiveControlClosedError('release-missing');
    }
    if (
      release.activationEnvelopeSha256 !== this.expectedReleaseEnvelopeSha256 ||
      release.pointerRevision !== this.expectedReleasePointerRevision
    ) {
      throw new StagingChatLiveControlClosedError('release-mismatched');
    }
  }

  private assertWindow(now: Date): void {
    const current = now.getTime();
    if (!Number.isFinite(current)) {
      throw new StagingChatLiveControlClosedError('unavailable');
    }
    if (this.lastTrustedTimeMs !== null && current < this.lastTrustedTimeMs) {
      throw new StagingChatLiveControlClosedError('clock-rollback');
    }
    this.lastTrustedTimeMs = current;
    const notBefore = Number(this.expected.not_before_ms);
    const expiresAt = Number(this.expected.expires_at_ms);
    if (current < notBefore) {
      throw new StagingChatLiveControlClosedError('not-yet-valid');
    }
    if (current >= expiresAt) {
      throw new StagingChatLiveControlClosedError('expired');
    }
  }

  private assertSnapshot(observed: Record<string, string>): void {
    const keys = Object.keys(observed).sort();
    if (keys.length === 0) {
      throw new StagingChatLiveControlClosedError('missing');
    }
    if (
      keys.length !== SNAPSHOT_KEYS.length ||
      keys.some((key, index) => key !== SNAPSHOT_KEYS[index])
    ) {
      throw new StagingChatLiveControlClosedError('malformed');
    }
    const snapshot = observed as unknown as ControlSnapshot;
    if (snapshot.enabled !== '0' && snapshot.enabled !== '1') {
      throw new StagingChatLiveControlClosedError('malformed');
    }
    if (snapshot.enabled === '0') {
      throw new StagingChatLiveControlClosedError('disabled');
    }
    for (const key of SNAPSHOT_KEYS) {
      if (snapshot[key] !== this.expected[key]) {
        throw new StagingChatLiveControlClosedError('mismatched');
      }
    }
  }
}

function validateExpectation(
  expectation: StagingChatLiveControlExpectation,
): void {
  const notBefore = expectation.notBefore.getTime();
  const expiresAt = expectation.expiresAt.getTime();
  const invalid =
    !CONTROL_ID.test(expectation.controlId) ||
    !SHA256.test(expectation.authorityDigest) ||
    !SHA256.test(expectation.releaseEnvelopeSha256) ||
    !Number.isSafeInteger(expectation.generation) ||
    expectation.generation < 1 ||
    !Number.isSafeInteger(expectation.releasePointerRevision) ||
    expectation.releasePointerRevision < 1 ||
    !Number.isFinite(notBefore) ||
    !Number.isFinite(expiresAt) ||
    notBefore >= expiresAt ||
    expiresAt - notBefore > MAXIMUM_VALIDITY_WINDOW_MS;
  if (invalid) {
    throw new StagingChatLiveControlClosedError('invalid-expectation');
  }
}

function sha256(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex');
}
