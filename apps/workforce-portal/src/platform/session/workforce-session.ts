import 'server-only';
import {setTimeout as delay} from 'node:timers/promises';
import {refreshAuthorizationTokens} from '@/platform/auth/oidc';
import type {OpaqueSessionId} from './contracts';
import {
  acquireRefreshLease,
  deleteSession,
  readSession,
  releaseRefreshLease,
  writeSession,
} from './redis-token-vault';

const REFRESH_SKEW_MILLISECONDS = 60_000;
const REFRESH_WAIT_ATTEMPTS = 4;
const REFRESH_WAIT_MILLISECONDS = 50;

type StoredSession = NonNullable<Awaited<ReturnType<typeof readSession>>>;

function isUsable(record: StoredSession, now = Date.now()): boolean {
  return (
    record.session.mfaSatisfied &&
    record.session.expiresAt.getTime() > now &&
    record.tokenSet.expiresAt.getTime() > now + REFRESH_SKEW_MILLISECONDS
  );
}

export async function ensureFreshWorkforceSession(
  sessionId: OpaqueSessionId,
  options: {readonly forceRefresh?: boolean} = {},
): Promise<StoredSession | null> {
  const current = await readSession(sessionId);
  if (
    current === null ||
    !current.session.mfaSatisfied ||
    current.session.expiresAt.getTime() <= Date.now()
  ) {
    await deleteSession(sessionId);
    return null;
  }
  if (!options.forceRefresh && isUsable(current)) return current;
  if (current.tokenSet.refreshToken === undefined) {
    await deleteSession(sessionId);
    return null;
  }

  const lease = await acquireRefreshLease(sessionId);
  if (lease === null) {
    for (let attempt = 0; attempt < REFRESH_WAIT_ATTEMPTS; attempt += 1) {
      await delay(REFRESH_WAIT_MILLISECONDS);
      const refreshed = await readSession(sessionId);
      if (refreshed !== null && isUsable(refreshed)) return refreshed;
    }
    return null;
  }

  try {
    const latest = await readSession(sessionId);
    if (latest === null) return null;
    if (!options.forceRefresh && isUsable(latest)) return latest;
    if (latest.tokenSet.refreshToken === undefined) {
      await deleteSession(sessionId);
      return null;
    }
    const refreshed = await refreshAuthorizationTokens({
      refreshToken: latest.tokenSet.refreshToken,
    });
    await writeSession(latest.session, refreshed, {requireExisting: true});
    return {session: latest.session, tokenSet: refreshed};
  } catch {
    await deleteSession(sessionId);
    return null;
  } finally {
    await releaseRefreshLease(sessionId, lease).catch(() => undefined);
  }
}
