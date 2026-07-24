import {cookies} from 'next/headers';
import {NextResponse} from 'next/server';
import {hasExactOrigin} from '@vfbiz/portal-session-core';
import {revokeOidcSession} from '@/platform/auth/oidc';
import {readWorkforcePortalEnvironment} from '@/platform/config/environment';
import type {OpaqueSessionId} from '@/platform/session/contracts';
import {
  deleteSubjectSessions,
  listSubjectSessions,
  readSession,
} from '@/platform/session/redis-token-vault';

async function current() {
  const environment = readWorkforcePortalEnvironment();
  const cookieStore = await cookies();
  const rawId = cookieStore.get(environment.WORKFORCE_SESSION_COOKIE_NAME)?.value;
  if (rawId === undefined) return null;
  const record = await readSession(rawId as OpaqueSessionId);
  return record === null ? null : {environment, record};
}

export async function GET() {
  try {
    const active = await current();
    if (active === null) {
      return NextResponse.json(
        {error: 'session_required'},
        {headers: {'Cache-Control': 'no-store'}, status: 401},
      );
    }
    const sessions = await listSubjectSessions(active.record.session.subject);
    return NextResponse.json(
      sessions.map(({session}) => ({
        authenticatedAt: session.authenticatedAt,
        deviceLabel: session.deviceLabel,
        emailVerified: session.emailVerified,
        expiresAt: session.expiresAt,
        id: session.id,
        isCurrent: session.id === active.record.session.id,
        lastSeenAt: session.lastSeenAt,
        mfaSatisfied: session.mfaSatisfied,
        networkHint: session.networkHint,
        userAgentSummary: session.userAgentSummary,
      })),
      {headers: {'Cache-Control': 'private, no-store'}},
    );
  } catch {
    return NextResponse.json(
      {error: 'session_service_unavailable'},
      {headers: {'Cache-Control': 'no-store'}, status: 503},
    );
  }
}

export async function DELETE(request: Request) {
  if (!hasExactOrigin(request)) {
    return NextResponse.json(
      {error: 'invalid_origin'},
      {headers: {'Cache-Control': 'no-store'}, status: 403},
    );
  }
  try {
    const active = await current();
    if (active === null) {
      return NextResponse.json(
        {error: 'session_required'},
        {headers: {'Cache-Control': 'no-store'}, status: 401},
      );
    }
    const sessions = await listSubjectSessions(active.record.session.subject);
    await Promise.all(
      sessions.map(({tokenSet}) =>
        revokeOidcSession(tokenSet.refreshToken),
      ),
    );
    const revokedCount = await deleteSubjectSessions(
      active.record.session.subject,
    );
    const response = NextResponse.json(
      {revokedCount},
      {headers: {'Cache-Control': 'no-store'}},
    );
    response.cookies.delete(active.environment.WORKFORCE_SESSION_COOKIE_NAME);
    return response;
  } catch {
    return NextResponse.json(
      {error: 'session_service_unavailable'},
      {headers: {'Cache-Control': 'no-store'}, status: 503},
    );
  }
}
