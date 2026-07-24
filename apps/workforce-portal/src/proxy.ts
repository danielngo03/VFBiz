import {NextResponse, type NextRequest} from 'next/server';

const protectedPrefixes = ['/authorization', '/audit'];

export function proxy(request: NextRequest) {
  const isProtected = protectedPrefixes.some((prefix) =>
    request.nextUrl.pathname.startsWith(prefix),
  );
  if (!isProtected) return NextResponse.next();

  const cookieName = process.env.WORKFORCE_SESSION_COOKIE_NAME ?? 'vfbiz-workforce-session';
  if (request.cookies.has(cookieName)) return NextResponse.next();

  const signIn = new URL('/sign-in', request.url);
  signIn.searchParams.set('returnTo', request.nextUrl.pathname);
  return NextResponse.redirect(signIn);
}

export const config = {
  matcher: ['/authorization/:path*', '/audit/:path*'],
};
