import {cookies} from 'next/headers';
import {NextResponse} from 'next/server';
import {
  exchangeAuthorizationCode,
  verifyIdTokenClaims,
} from '@/platform/auth/oidc';
import {readWorkforcePortalEnvironment} from '@/platform/config/environment';
import {
  consumeOidcAttempt,
  newOpaqueSessionId,
  writeSession,
} from '@/platform/session/redis-token-vault';
import {workforceClientContext} from '@/platform/session/client-context';

export async function GET(request: Request) {
  const parameters = new URL(request.url).searchParams;
  const code = parameters.get('code');
  const state = parameters.get('state');
  const cookieStore = await cookies();
  const attemptId = cookieStore.get('vfbiz-workforce-oidc-attempt')?.value;
  if (!code || !state || !attemptId) {
    return NextResponse.json(
      {error: 'invalid_oidc_callback'},
      {headers: {'Cache-Control': 'no-store'}, status: 400},
    );
  }
  let attempt: Awaited<ReturnType<typeof consumeOidcAttempt>>;
  try {
    attempt = await consumeOidcAttempt(attemptId);
  } catch {
    return NextResponse.json(
      {error: 'session_service_unavailable'},
      {headers: {'Cache-Control': 'no-store'}, status: 503},
    );
  }
  if (attempt === null || attempt.state !== state) {
    return NextResponse.json(
      {error: 'invalid_oidc_state'},
      {headers: {'Cache-Control': 'no-store'}, status: 400},
    );
  }
  let tokens: Awaited<ReturnType<typeof exchangeAuthorizationCode>>;
  let claims: Awaited<ReturnType<typeof verifyIdTokenClaims>>;
  try {
    tokens = await exchangeAuthorizationCode({
      code,
      codeVerifier: attempt.codeVerifier,
    });
    claims = await verifyIdTokenClaims(tokens.idToken);
  } catch {
    return NextResponse.json(
      {error: 'identity_provider_response_invalid'},
      {headers: {'Cache-Control': 'no-store'}, status: 502},
    );
  }
  if (claims.nonce !== attempt.nonce) {
    return NextResponse.json(
      {error: 'invalid_oidc_nonce'},
      {headers: {'Cache-Control': 'no-store'}, status: 400},
    );
  }
  if (!claims.emailVerified || !claims.mfaSatisfied) {
    return NextResponse.json(
      {error: 'workforce_assurance_required'},
      {headers: {'Cache-Control': 'no-store'}, status: 403},
    );
  }
  const sessionId = newOpaqueSessionId();
  const authenticatedAt = new Date();
  const client = workforceClientContext(request);
  const sessionExpiresAt = new Date(
    Date.now() +
      readWorkforcePortalEnvironment().WORKFORCE_SESSION_MAX_AGE_SECONDS * 1000,
  );
  try {
    await writeSession(
      {
        authenticatedAt,
        deviceLabel: client.deviceLabel,
        emailVerified: claims.emailVerified,
        entitlementRevision: 'unresolved',
        expiresAt: sessionExpiresAt,
        id: sessionId,
        mfaSatisfied: claims.mfaSatisfied,
        lastSeenAt: authenticatedAt,
        networkHint: client.networkHint,
        subject: claims.subject,
        userAgentSummary: client.userAgentSummary,
      },
      {
        accessToken: tokens.accessToken,
        expiresAt: tokens.expiresAt,
        ...(tokens.refreshToken === undefined
          ? {}
          : {refreshToken: tokens.refreshToken}),
      },
    );
  } catch {
    return NextResponse.json(
      {error: 'session_service_unavailable'},
      {headers: {'Cache-Control': 'no-store'}, status: 503},
    );
  }
  const environment = readWorkforcePortalEnvironment();
  const response = NextResponse.redirect(new URL(attempt.returnTo, request.url));
  response.headers.set('Cache-Control', 'no-store');
  response.cookies.delete('vfbiz-workforce-oidc-attempt');
  response.cookies.set(environment.WORKFORCE_SESSION_COOKIE_NAME, sessionId, {
    httpOnly: true,
    maxAge: Math.max(
      1,
      Math.floor((sessionExpiresAt.getTime() - Date.now()) / 1000),
    ),
    path: '/',
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
  });
  return response;
}
