import {cookies} from 'next/headers';
import {NextResponse} from 'next/server';
import {hasExactOrigin} from '@vfbiz/portal-session-core';
import {readWorkforcePortalEnvironment} from '@/platform/config/environment';
import {revokeOidcSession} from '@/platform/auth/oidc';
import {
  deleteSession,
  readSession,
} from '@/platform/session/redis-token-vault';
import type {OpaqueSessionId} from '@/platform/session/contracts';

export async function POST(request: Request) {
  if (!hasExactOrigin(request)) {
    return NextResponse.json(
      {error: 'invalid_origin'},
      {headers: {'Cache-Control': 'no-store'}, status: 403},
    );
  }
  const environment = readWorkforcePortalEnvironment();
  const cookieStore = await cookies();
  const rawSessionId = cookieStore.get(
    environment.WORKFORCE_SESSION_COOKIE_NAME,
  )?.value;
  if (rawSessionId !== undefined) {
    const sessionId = rawSessionId as OpaqueSessionId;
    try {
      const stored = await readSession(sessionId);
      await deleteSession(sessionId);
      await revokeOidcSession(stored?.tokenSet.refreshToken);
    } catch {
      const response = NextResponse.json(
        {error: 'session_service_unavailable'},
        {headers: {'Cache-Control': 'no-store'}, status: 503},
      );
      response.cookies.delete(environment.WORKFORCE_SESSION_COOKIE_NAME);
      return response;
    }
  }
  const response = NextResponse.redirect(new URL('/sign-in', request.url), 303);
  response.headers.set('Cache-Control', 'no-store');
  response.cookies.delete(environment.WORKFORCE_SESSION_COOKIE_NAME);
  return response;
}
