import 'server-only';
import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
  randomUUID,
} from 'node:crypto';
import Redis from 'ioredis';
import {readWorkforcePortalEnvironment} from '@/platform/config/environment';
import type {
  OpaqueSessionId,
  WorkforceBffSession,
  WorkforceTokenSet,
} from './contracts';

const OIDC_ATTEMPT_TTL_SECONDS = 10 * 60;
const REFRESH_LEASE_TTL_MILLISECONDS = 10_000;

interface OidcAttempt {
  readonly state: string;
  readonly nonce: string;
  readonly codeVerifier: string;
  readonly returnTo: string;
}

interface VaultRecord {
  readonly session: {
    readonly id: string;
    readonly authenticatedAt: string;
    readonly deviceLabel: string | null;
    readonly emailVerified: boolean;
    readonly subject: string;
    readonly mfaSatisfied: boolean;
    readonly entitlementRevision: string;
    readonly expiresAt: string;
    readonly lastSeenAt: string;
    readonly networkHint: string | null;
    readonly userAgentSummary: string | null;
  };
  readonly tokenSet: {
    readonly accessToken: string;
    readonly refreshToken?: string;
    readonly expiresAt: string;
  };
}

let redisClient: Redis | undefined;

function redis(): Redis {
  if (redisClient === undefined) {
    redisClient = new Redis(readWorkforcePortalEnvironment().WORKFORCE_REDIS_URL, {
      connectTimeout: 2_000,
      enableReadyCheck: true,
      maxRetriesPerRequest: 1,
    });
  }
  return redisClient;
}

function keyFor(prefix: string, value: string): string {
  const digest = createHash('sha256').update(value).digest('hex');
  return `vfbiz:workforce:${prefix}:${digest}`;
}

function encryptionKey(): Buffer {
  return Buffer.from(
    readWorkforcePortalEnvironment().WORKFORCE_TOKEN_VAULT_KEY,
    'base64',
  );
}

function encrypt(value: unknown): string {
  const initializationVector = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', encryptionKey(), initializationVector);
  const ciphertext = Buffer.concat([
    cipher.update(JSON.stringify(value), 'utf8'),
    cipher.final(),
  ]);
  return [
    initializationVector.toString('base64url'),
    cipher.getAuthTag().toString('base64url'),
    ciphertext.toString('base64url'),
  ].join('.');
}

function decrypt<T>(value: string): T {
  const [encodedIv, encodedTag, encodedCiphertext] = value.split('.');
  if (!encodedIv || !encodedTag || !encodedCiphertext) {
    throw new Error('Invalid token-vault record.');
  }
  const decipher = createDecipheriv(
    'aes-256-gcm',
    encryptionKey(),
    Buffer.from(encodedIv, 'base64url'),
  );
  decipher.setAuthTag(Buffer.from(encodedTag, 'base64url'));
  return JSON.parse(
    Buffer.concat([
      decipher.update(Buffer.from(encodedCiphertext, 'base64url')),
      decipher.final(),
    ]).toString('utf8'),
  ) as T;
}

export function newOpaqueSessionId(): OpaqueSessionId {
  return randomBytes(32).toString('base64url') as OpaqueSessionId;
}

export async function saveOidcAttempt(
  attemptId: string,
  attempt: OidcAttempt,
): Promise<void> {
  await redis().set(
    keyFor('oidc-attempt', attemptId),
    encrypt(attempt),
    'EX',
    OIDC_ATTEMPT_TTL_SECONDS,
  );
}

export async function consumeOidcAttempt(
  attemptId: string,
): Promise<OidcAttempt | null> {
  const key = keyFor('oidc-attempt', attemptId);
  const value = await redis().getdel(key);
  return value === null ? null : decrypt<OidcAttempt>(value);
}

export async function writeSession(
  session: WorkforceBffSession,
  tokenSet: WorkforceTokenSet,
  options: {readonly requireExisting?: boolean} = {},
): Promise<void> {
  const record: VaultRecord = {
    session: {
      ...session,
      authenticatedAt: session.authenticatedAt.toISOString(),
      expiresAt: session.expiresAt.toISOString(),
      lastSeenAt: session.lastSeenAt.toISOString(),
    },
    tokenSet: {
      ...tokenSet,
      expiresAt: tokenSet.expiresAt.toISOString(),
    },
  };
  const ttl = Math.max(
    1,
    Math.min(
      readWorkforcePortalEnvironment().WORKFORCE_SESSION_MAX_AGE_SECONDS,
      Math.floor((session.expiresAt.getTime() - Date.now()) / 1000),
    ),
  );
  const subjectIndexKey = keyFor('subject-sessions', session.subject);
  const activityKey = keyFor('session-activity', session.id);
  const sessionKey = keyFor('session', session.id);
  const logoutFenceKey = keyFor('logout-fence', session.id);
  if (options.requireExisting === true) {
    const result = await redis().eval(
      [
        'if redis.call("exists", KEYS[1]) == 0 then return 0 end',
        'if redis.call("exists", KEYS[2]) == 1 then return 0 end',
        'redis.call("set", KEYS[1], ARGV[1], "EX", ARGV[2])',
        'redis.call("set", KEYS[3], ARGV[3], "EX", ARGV[2])',
        'redis.call("sadd", KEYS[4], ARGV[4])',
        'redis.call("expire", KEYS[4], ARGV[2])',
        'return 1',
      ].join('\n'),
      4,
      sessionKey,
      logoutFenceKey,
      activityKey,
      subjectIndexKey,
      encrypt(record),
      String(ttl),
      String(session.lastSeenAt.getTime()),
      session.id,
    );
    if (result !== 1) throw new Error('Session was revoked during refresh.');
    return;
  }
  await redis()
    .multi()
    .del(logoutFenceKey)
    .set(sessionKey, encrypt(record), 'EX', ttl)
    .set(activityKey, String(session.lastSeenAt.getTime()), 'EX', ttl)
    .sadd(subjectIndexKey, session.id)
    .expire(subjectIndexKey, ttl)
    .exec();
}

export async function readSession(
  sessionId: OpaqueSessionId,
  options: {readonly touch?: boolean} = {},
): Promise<{session: WorkforceBffSession; tokenSet: WorkforceTokenSet} | null> {
  const sessionKey = keyFor('session', sessionId);
  const activityKey = keyFor('session-activity', sessionId);
  const [value, activity] = await redis().mget(sessionKey, activityKey);
  if (value === null) return null;
  const record = decrypt<VaultRecord>(value);
  const now = Date.now();
  const lastSeenAt =
    activity !== null && Number.isSafeInteger(Number(activity))
      ? Number(activity)
      : new Date(record.session.lastSeenAt).getTime();
  const environment = readWorkforcePortalEnvironment();
  if (
    new Date(record.session.expiresAt).getTime() <= now ||
    now - lastSeenAt >
      environment.WORKFORCE_SESSION_IDLE_TIMEOUT_SECONDS * 1_000
  ) {
    await redis()
      .multi()
      .del(sessionKey, activityKey)
      .srem(keyFor('subject-sessions', record.session.subject), sessionId)
      .exec();
    return null;
  }
  const touch = options.touch ?? true;
  if (touch) {
    const ttl = Math.max(
      1,
      Math.min(
        environment.WORKFORCE_SESSION_MAX_AGE_SECONDS,
        Math.floor(
          (new Date(record.session.expiresAt).getTime() - now) / 1_000,
        ),
      ),
    );
    await redis().set(activityKey, String(now), 'EX', ttl);
  }
  return {
    session: {
      ...record.session,
      id: record.session.id as OpaqueSessionId,
      authenticatedAt: new Date(record.session.authenticatedAt),
      expiresAt: new Date(record.session.expiresAt),
      lastSeenAt: new Date(touch ? now : lastSeenAt),
    },
    tokenSet: {
      ...record.tokenSet,
      expiresAt: new Date(record.tokenSet.expiresAt),
    },
  };
}

export async function deleteSession(sessionId: OpaqueSessionId): Promise<void> {
  const stored = await readSession(sessionId, {touch: false});
  const transaction = redis()
    .multi()
    .set(
      keyFor('logout-fence', sessionId),
      '1',
      'EX',
      readWorkforcePortalEnvironment().WORKFORCE_SESSION_MAX_AGE_SECONDS,
    )
    .del(
      keyFor('session', sessionId),
      keyFor('session-activity', sessionId),
    );
  if (stored !== null) {
    transaction.srem(
      keyFor('subject-sessions', stored.session.subject),
      sessionId,
    );
  }
  await transaction.exec();
}

export async function listSubjectSessions(
  subject: string,
): Promise<readonly {session: WorkforceBffSession; tokenSet: WorkforceTokenSet}[]> {
  const ids = await redis().smembers(keyFor('subject-sessions', subject));
  const records = await Promise.all(
    ids.map((id) => readSession(id as OpaqueSessionId, {touch: false})),
  );
  const active = records.filter(
    (
      record,
    ): record is {
      session: WorkforceBffSession;
      tokenSet: WorkforceTokenSet;
    } => record !== null,
  );
  if (active.length !== ids.length) {
    const activeIds = new Set(active.map((record) => record.session.id));
    const staleIds = ids.filter((id) => !activeIds.has(id as OpaqueSessionId));
    if (staleIds.length > 0) {
      await redis().srem(keyFor('subject-sessions', subject), ...staleIds);
    }
  }
  return active;
}

export async function deleteSubjectSessions(subject: string): Promise<number> {
  const records = await listSubjectSessions(subject);
  if (records.length === 0) return 0;
  const transaction = redis().multi();
  for (const record of records) {
    transaction.set(
      keyFor('logout-fence', record.session.id),
      '1',
      'EX',
      readWorkforcePortalEnvironment().WORKFORCE_SESSION_MAX_AGE_SECONDS,
    );
    transaction.del(
      keyFor('session', record.session.id),
      keyFor('session-activity', record.session.id),
    );
  }
  transaction.del(keyFor('subject-sessions', subject));
  await transaction.exec();
  return records.length;
}

export async function acquireRefreshLease(
  sessionId: OpaqueSessionId,
): Promise<string | null> {
  const token = randomUUID();
  const result = await redis().set(
    keyFor('refresh-lease', sessionId),
    token,
    'PX',
    REFRESH_LEASE_TTL_MILLISECONDS,
    'NX',
  );
  return result === 'OK' ? token : null;
}

export async function releaseRefreshLease(
  sessionId: OpaqueSessionId,
  token: string,
): Promise<void> {
  await redis().eval(
    [
      'if redis.call("get", KEYS[1]) == ARGV[1] then',
      '  return redis.call("del", KEYS[1])',
      'end',
      'return 0',
    ].join('\n'),
    1,
    keyFor('refresh-lease', sessionId),
    token,
  );
}

export function newRunIdentifiers() {
  return {
    attemptId: randomUUID(),
    nonce: randomBytes(24).toString('base64url'),
    state: randomBytes(24).toString('base64url'),
    codeVerifier: randomBytes(48).toString('base64url'),
  };
}
