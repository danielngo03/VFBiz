import "server-only";
import {
  createHash,
  randomBytes,
  randomUUID,
} from "node:crypto";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";
import type {
  CustomerBffSession,
  CustomerTokenSet,
  OpaqueCustomerSessionId,
} from "./contracts";
import {
  customerSessionKey as key,
  customerSessionRedis as redis,
  decryptVaultRecord as decrypt,
  encryptVaultRecord as encrypt,
} from "./redis-vault-runtime";

export {
  consumeAttempt,
  newAttempt,
  saveAttempt,
} from "./oidc-attempt-store";
export {
  acquireRefreshLease,
  beginBackchannelLogoutToken,
  completeBackchannelLogoutToken,
  releaseBackchannelLogoutToken,
  releaseRefreshLease,
} from "./session-coordination";
export type { BackchannelLogoutClaim } from "./session-coordination";

const PROVIDER_REVOCATION_TTL_SECONDS = 7 * 24 * 60 * 60;
const PROVIDER_REVOCATION_LEASE_MILLISECONDS = 30_000;

interface StoredRecord {
  readonly session: Omit<
    CustomerBffSession,
    "authenticatedAt" | "expiresAt" | "id" | "lastSeenAt"
  > & {
    readonly authenticatedAt: string;
    readonly expiresAt: string;
    readonly id: string;
    readonly lastSeenAt: string;
  };
  readonly tokenSet: Omit<CustomerTokenSet, "expiresAt"> & {
    readonly expiresAt: string;
  };
}

interface StoredProviderRevocation {
  readonly attemptCount: number;
  readonly createdAt: string;
  readonly lastAttemptAt?: string;
  readonly providerSessionId: string;
  readonly refreshToken: string;
}

interface StoredProviderRevocationTerminal {
  readonly attemptCount: number;
  readonly createdAt: string;
  readonly finalizedAt: string;
  readonly providerSessionIdHash: string;
  readonly status: "retry_required";
}

export interface ProviderRevocationTask {
  readonly attemptCount: number;
  readonly createdAt: Date;
  readonly id: string;
  readonly lastAttemptAt?: Date;
  readonly providerSessionId: string;
  readonly refreshToken: string;
}

export interface CustomerSessionRecord {
  readonly revision: string;
  readonly session: CustomerBffSession;
  readonly tokenSet: CustomerTokenSet;
}

function providerRevocationQueueKey(): string {
  return key("provider-revocation-queue", "v1");
}

function providerRevocationLeaseKey(): string {
  return key("provider-revocation-lease", "v1");
}

function sessionIndexKey(): string {
  return key("session-index", "v1");
}

function sessionIndexMetadata(
  id: OpaqueCustomerSessionId,
  subject: string,
  providerSessionId: string,
): string {
  return JSON.stringify({
    activityKey: key("activity", id),
    providerFenceKey: key("provider-logout-fence", providerSessionId),
    providerSetKey: key("provider-sessions", providerSessionId),
    revisionKey: key("session-revision", id),
    sessionKey: key("session", id),
    subjectSetKey: key("subject-sessions", subject),
  });
}

export function newSessionId(): OpaqueCustomerSessionId {
  return randomBytes(32).toString("base64url") as OpaqueCustomerSessionId;
}

export async function writeSession(
  session: CustomerBffSession,
  tokenSet: CustomerTokenSet,
  options: { readonly expectedRevision?: string } = {},
): Promise<string | null> {
  const environment = readCustomerPortalEnvironment();
  const ttl = Math.max(
    1,
    Math.min(
      environment.CUSTOMER_SESSION_MAX_AGE_SECONDS,
      Math.floor((session.expiresAt.getTime() - Date.now()) / 1_000),
    ),
  );
  const record: StoredRecord = {
    session: {
      ...session,
      authenticatedAt: session.authenticatedAt.toISOString(),
      expiresAt: session.expiresAt.toISOString(),
      lastSeenAt: session.lastSeenAt.toISOString(),
    },
    tokenSet: { ...tokenSet, expiresAt: tokenSet.expiresAt.toISOString() },
  };
  const revision = randomUUID();
  const result = await redis().eval(
    `
      local subjectFence = redis.call("get", KEYS[6])
      if subjectFence and tonumber(ARGV[8]) <= tonumber(subjectFence) then
        return 0
      end
      if redis.call("exists", KEYS[7]) == 1 then return 0 end
      if ARGV[6] ~= "" then
        if redis.call("exists", KEYS[1]) == 0 then return 0 end
        if redis.call("get", KEYS[5]) ~= ARGV[6] then return 0 end
      elseif redis.call("exists", KEYS[1]) == 1 then
        return 0
      end
      redis.call("set", KEYS[1], ARGV[1], "EX", ARGV[2])
      redis.call("set", KEYS[2], ARGV[3], "EX", ARGV[2])
      redis.call("sadd", KEYS[3], ARGV[5])
      redis.call("expire", KEYS[3], ARGV[4])
      redis.call("sadd", KEYS[4], ARGV[5])
      redis.call("expire", KEYS[4], ARGV[4])
      redis.call("set", KEYS[5], ARGV[7], "EX", ARGV[2])
      redis.call("hset", KEYS[8], ARGV[5], ARGV[9])
      return 1
    `,
    8,
    key("session", session.id),
    key("activity", session.id),
    key("subject-sessions", session.subject),
    key("provider-sessions", session.providerSessionId),
    key("session-revision", session.id),
    key("subject-logout-fence", session.subject),
    key("provider-logout-fence", session.providerSessionId),
    sessionIndexKey(),
    encrypt(record),
    String(ttl),
    String(session.lastSeenAt.getTime()),
    String(environment.CUSTOMER_SESSION_MAX_AGE_SECONDS),
    session.id,
    options.expectedRevision ?? "",
    revision,
    String(session.authenticatedAt.getTime()),
    sessionIndexMetadata(session.id, session.subject, session.providerSessionId),
  );
  return Number(result) === 1 ? revision : null;
}

export async function readSession(
  id: OpaqueCustomerSessionId,
  options: { readonly touch?: boolean } = {},
): Promise<CustomerSessionRecord | null> {
  const [encrypted, activity, revision] = await redis().mget(
    key("session", id),
    key("activity", id),
    key("session-revision", id),
  );
  if (encrypted === null || revision === null) {
    if (encrypted !== null) {
      await redis()
        .multi()
        .del(
          key("session", id),
          key("activity", id),
          key("session-revision", id),
        )
        .hdel(sessionIndexKey(), id)
        .exec();
    }
    return null;
  }
  let record: StoredRecord;
  try {
    record = decrypt<StoredRecord>(encrypted);
  } catch {
    await redis().multi().del(key("session", id), key("activity", id)).exec();
    return null;
  }
  const environment = readCustomerPortalEnvironment();
  const now = Date.now();
  const lastSeen =
    activity === null
      ? new Date(record.session.lastSeenAt).getTime()
      : Number(activity);
  if (
    new Date(record.session.expiresAt).getTime() <= now ||
    now - lastSeen > environment.CUSTOMER_SESSION_IDLE_TIMEOUT_SECONDS * 1_000
  ) {
    await deleteSession(
      id,
      record.session.subject,
      record.session.providerSessionId,
    );
    return null;
  }
  if (options.touch ?? true) {
    const ttl = Math.max(
      1,
      Math.floor((new Date(record.session.expiresAt).getTime() - now) / 1_000),
    );
    await redis().set(key("activity", id), String(now), "EX", ttl);
  }
  return {
    revision,
    session: {
      ...record.session,
      authenticatedAt: new Date(record.session.authenticatedAt),
      expiresAt: new Date(record.session.expiresAt),
      id: record.session.id as OpaqueCustomerSessionId,
      lastSeenAt: new Date((options.touch ?? true) ? now : lastSeen),
    },
    tokenSet: {
      ...record.tokenSet,
      expiresAt: new Date(record.tokenSet.expiresAt),
    },
  };
}

export async function deleteSession(
  id: OpaqueCustomerSessionId,
  knownSubject?: string,
  knownProviderSessionId?: string,
): Promise<void> {
  const record =
    knownSubject === undefined ? await readSession(id, { touch: false }) : null;
  const subject = knownSubject ?? record?.session.subject;
  const providerSessionId =
    knownProviderSessionId ?? record?.session.providerSessionId;
  const transaction = redis()
    .multi()
    .del(
      key("session", id),
      key("activity", id),
      key("session-revision", id),
    )
    .hdel(sessionIndexKey(), id);
  if (subject !== undefined) {
    transaction.srem(key("subject-sessions", subject), id);
  }
  if (providerSessionId !== undefined) {
    transaction.srem(key("provider-sessions", providerSessionId), id);
  }
  await transaction.exec();
}

export async function listSessions(subject: string) {
  const ids = await redis().smembers(key("subject-sessions", subject));
  const records = await Promise.all(
    ids.map((id) =>
      readSession(id as OpaqueCustomerSessionId, { touch: false }),
    ),
  );
  return records.filter((record) => record !== null);
}

export async function deleteAllSessions(subject: string): Promise<number> {
  const environment = readCustomerPortalEnvironment();
  const result = await redis().eval(
    `
      redis.call("set", KEYS[2], ARGV[1], "EX", ARGV[2])
      local ids = redis.call("smembers", KEYS[1])
      local deleted = 0
      for _, id in ipairs(ids) do
        local encoded = redis.call("hget", KEYS[3], id)
        if encoded then
          local metadata = cjson.decode(encoded)
          redis.call("set", metadata.providerFenceKey, "1", "EX", ARGV[2])
          redis.call("del", metadata.sessionKey, metadata.activityKey, metadata.revisionKey)
          redis.call("srem", metadata.providerSetKey, id)
          redis.call("hdel", KEYS[3], id)
          deleted = deleted + 1
        end
      end
      redis.call("del", KEYS[1])
      return deleted
    `,
    3,
    key("subject-sessions", subject),
    key("subject-logout-fence", subject),
    sessionIndexKey(),
    String(Date.now()),
    String(environment.CUSTOMER_SESSION_MAX_AGE_SECONDS),
  );
  return Number(result);
}

export async function deleteProviderSessions(
  providerSessionId: string,
): Promise<number> {
  const environment = readCustomerPortalEnvironment();
  const providerKey = key("provider-sessions", providerSessionId);
  const result = await redis().eval(
    `
      redis.call("set", KEYS[2], "1", "EX", ARGV[1])
      local ids = redis.call("smembers", KEYS[1])
      local deleted = 0
      for _, id in ipairs(ids) do
        local encoded = redis.call("hget", KEYS[3], id)
        if encoded then
          local metadata = cjson.decode(encoded)
          redis.call("del", metadata.sessionKey, metadata.activityKey, metadata.revisionKey)
          redis.call("srem", metadata.subjectSetKey, id)
          redis.call("hdel", KEYS[3], id)
          deleted = deleted + 1
        end
      end
      redis.call("del", KEYS[1])
      return deleted
    `,
    3,
    providerKey,
    key("provider-logout-fence", providerSessionId),
    sessionIndexKey(),
    String(environment.CUSTOMER_SESSION_MAX_AGE_SECONDS),
  );
  return Number(result);
}

export async function enqueueProviderRevocation(input: {
  readonly providerSessionId: string;
  readonly refreshToken: string;
  readonly now?: Date;
}): Promise<string> {
  const id = randomUUID();
  const createdAt = input.now ?? new Date();
  const record: StoredProviderRevocation = {
    attemptCount: 0,
    createdAt: createdAt.toISOString(),
    providerSessionId: input.providerSessionId,
    refreshToken: input.refreshToken,
  };
  await redis()
    .multi()
    .set(
      key("provider-revocation", id),
      encrypt(record),
      "EX",
      PROVIDER_REVOCATION_TTL_SECONDS,
    )
    .zadd(providerRevocationQueueKey(), createdAt.getTime(), id)
    .exec();
  return id;
}

export async function acquireProviderRevocationLease(): Promise<string | null> {
  const lease = randomUUID();
  const result = await redis().set(
    providerRevocationLeaseKey(),
    lease,
    "PX",
    PROVIDER_REVOCATION_LEASE_MILLISECONDS,
    "NX",
  );
  return result === "OK" ? lease : null;
}

export async function renewProviderRevocationLease(
  lease: string,
): Promise<boolean> {
  const result = await redis().eval(
    'if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("pexpire", KEYS[1], ARGV[2]) end return 0',
    1,
    providerRevocationLeaseKey(),
    lease,
    String(PROVIDER_REVOCATION_LEASE_MILLISECONDS),
  );
  return Number(result) === 1;
}

export async function releaseProviderRevocationLease(
  lease: string,
): Promise<void> {
  await redis().eval(
    'if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("del", KEYS[1]) end return 0',
    1,
    providerRevocationLeaseKey(),
    lease,
  );
}

export async function readDueProviderRevocations(
  now = new Date(),
  limit = 25,
): Promise<readonly ProviderRevocationTask[]> {
  const safeLimit = Math.max(1, Math.min(100, Math.trunc(limit)));
  const ids = await redis().zrangebyscore(
    providerRevocationQueueKey(),
    "-inf",
    now.getTime(),
    "LIMIT",
    0,
    safeLimit,
  );
  if (ids.length === 0) return [];
  const values = await redis().mget(
    ...ids.map((id) => key("provider-revocation", id)),
  );
  const missingIds: string[] = [];
  const tasks: ProviderRevocationTask[] = [];
  for (const [index, value] of values.entries()) {
    const id = ids[index];
    if (id === undefined) continue;
    if (value === null) {
      missingIds.push(id);
      continue;
    }
    try {
      const record = decrypt<StoredProviderRevocation>(value);
      tasks.push({
        attemptCount: record.attemptCount,
        createdAt: new Date(record.createdAt),
        id,
        ...(record.lastAttemptAt === undefined
          ? {}
          : { lastAttemptAt: new Date(record.lastAttemptAt) }),
        providerSessionId: record.providerSessionId,
        refreshToken: record.refreshToken,
      });
    } catch {
      missingIds.push(id);
      await redis().del(key("provider-revocation", id));
    }
  }
  if (missingIds.length > 0) {
    await redis().zrem(providerRevocationQueueKey(), ...missingIds);
  }
  return tasks;
}

export async function completeProviderRevocation(
  id: string,
  lease: string,
): Promise<boolean> {
  const result = await redis().eval(
    `
      if redis.call("get", KEYS[1]) ~= ARGV[1] then return 0 end
      redis.call("del", KEYS[2])
      redis.call("zrem", KEYS[3], ARGV[2])
      return 1
    `,
    3,
    providerRevocationLeaseKey(),
    key("provider-revocation", id),
    providerRevocationQueueKey(),
    lease,
    id,
  );
  return Number(result) === 1;
}

export async function rescheduleProviderRevocation(
  task: ProviderRevocationTask,
  input: { readonly attemptedAt: Date; readonly nextAttemptAt: Date },
  lease: string,
): Promise<boolean> {
  const record: StoredProviderRevocation = {
    attemptCount: task.attemptCount + 1,
    createdAt: task.createdAt.toISOString(),
    lastAttemptAt: input.attemptedAt.toISOString(),
    providerSessionId: task.providerSessionId,
    refreshToken: task.refreshToken,
  };
  const result = await redis().eval(
    `
      if redis.call("get", KEYS[1]) ~= ARGV[1] then return 0 end
      if redis.call("exists", KEYS[2]) == 0 then
        redis.call("zrem", KEYS[3], ARGV[2])
        return 0
      end
      redis.call("set", KEYS[2], ARGV[3], "KEEPTTL")
      redis.call("zadd", KEYS[3], ARGV[4], ARGV[2])
      return 1
    `,
    3,
    providerRevocationLeaseKey(),
    key("provider-revocation", task.id),
    providerRevocationQueueKey(),
    lease,
    task.id,
    encrypt(record),
    String(input.nextAttemptAt.getTime()),
  );
  return Number(result) === 1;
}

export async function abandonProviderRevocation(
  task: ProviderRevocationTask,
  finalizedAt: Date,
  lease: string,
): Promise<boolean> {
  const terminal: StoredProviderRevocationTerminal = {
    attemptCount: task.attemptCount,
    createdAt: task.createdAt.toISOString(),
    finalizedAt: finalizedAt.toISOString(),
    providerSessionIdHash: createHash("sha256")
      .update(task.providerSessionId)
      .digest("hex"),
    status: "retry_required",
  };
  const result = await redis().eval(
    `
      if redis.call("get", KEYS[1]) ~= ARGV[1] then return 0 end
      redis.call("del", KEYS[2])
      redis.call("zrem", KEYS[3], ARGV[2])
      redis.call("set", KEYS[4], ARGV[3], "EX", ARGV[4])
      return 1
    `,
    4,
    providerRevocationLeaseKey(),
    key("provider-revocation", task.id),
    providerRevocationQueueKey(),
    key("provider-revocation-terminal", task.id),
    lease,
    task.id,
    JSON.stringify(terminal),
    String(PROVIDER_REVOCATION_TTL_SECONDS),
  );
  return Number(result) === 1;
}

export async function readProviderRevocationTerminal(
  id: string,
): Promise<StoredProviderRevocationTerminal | null> {
  const value = await redis().get(key("provider-revocation-terminal", id));
  return value === null
    ? null
    : (JSON.parse(value) as StoredProviderRevocationTerminal);
}

export async function deleteProviderRevocationTask(id: string): Promise<void> {
  await redis()
    .multi()
    .del(
      key("provider-revocation", id),
      key("provider-revocation-terminal", id),
    )
    .zrem(providerRevocationQueueKey(), id)
    .exec();
}
