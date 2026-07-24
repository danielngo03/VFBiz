import {cookies} from 'next/headers';
import {NextResponse} from 'next/server';
import {hasExactOrigin} from '@vfbiz/portal-session-core';
import {readWorkforcePortalEnvironment} from '@/platform/config/environment';
import type {OpaqueSessionId} from '@/platform/session/contracts';
import {ensureFreshWorkforceSession} from '@/platform/session/workforce-session';

export async function POST(request: Request) {
  if (!hasExactOrigin(request)) {
    return NextResponse.json({error: 'invalid_origin'}, {status: 403});
  }

  const environment = readWorkforcePortalEnvironment();
  const cookieStore = await cookies();
  const rawSessionId = cookieStore.get(
    environment.WORKFORCE_SESSION_COOKIE_NAME,
  )?.value;
  if (rawSessionId === undefined) {
    return NextResponse.json({error: 'session_required'}, {status: 401});
  }

  let refreshed: Awaited<ReturnType<typeof ensureFreshWorkforceSession>>;
  try {
    refreshed = await ensureFreshWorkforceSession(
      rawSessionId as OpaqueSessionId,
      {forceRefresh: true},
    );
  } catch {
    return NextResponse.json(
      {error: 'session_service_unavailable'},
      {headers: {'Cache-Control': 'no-store'}, status: 503},
    );
  }
  if (refreshed === null) {
    const response = NextResponse.json(
      {error: 'session_refresh_failed'},
      {status: 401},
    );
    response.cookies.delete(environment.WORKFORCE_SESSION_COOKIE_NAME);
    return response;
  }

  return new NextResponse(null, {
    headers: {'Cache-Control': 'no-store'},
    status: 204,
  });
}
