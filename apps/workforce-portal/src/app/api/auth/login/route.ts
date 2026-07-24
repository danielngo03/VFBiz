import {NextResponse} from 'next/server';
import {authorizationUrl} from '@/platform/auth/oidc';
import {
  newRunIdentifiers,
  saveOidcAttempt,
} from '@/platform/session/redis-token-vault';

function safeReturnTo(value: string | null): string {
  return value?.startsWith('/') &&
    !value.startsWith('//') &&
    !value.includes('\\') &&
    !value.includes('\0')
    ? value
    : '/authorization';
}

export async function GET(request: Request) {
  const identifiers = newRunIdentifiers();
  const returnTo = safeReturnTo(new URL(request.url).searchParams.get('returnTo'));
  try {
    await saveOidcAttempt(identifiers.attemptId, {...identifiers, returnTo});
  } catch {
    return NextResponse.json(
      {error: 'session_service_unavailable'},
      {headers: {'Cache-Control': 'no-store'}, status: 503},
    );
  }
  const response = NextResponse.redirect(authorizationUrl(identifiers));
  response.cookies.set('vfbiz-workforce-oidc-attempt', identifiers.attemptId, {
    httpOnly: true,
    maxAge: 10 * 60,
    path: '/api/auth/callback',
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
  });
  return response;
}
