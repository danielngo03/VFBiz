import { NextResponse, type NextRequest } from "next/server";

const protectedPrefixes = ["/account", "/chat"];

function contentSecurityPolicy(nonce: string): string {
  const isDevelopment = process.env.NODE_ENV === "development";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${
      isDevelopment ? " 'unsafe-eval'" : ""
    }`,
    // Next.js and the browser may emit framework/runtime style attributes.
    // Scripts remain nonce-restricted; styles follow Next's documented CSP
    // compatibility profile until hash-based style delivery is available.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const policy = contentSecurityPolicy(nonce);
  const requestHeaders = new Headers(request.headers);
  const enforceCsp = process.env.CUSTOMER_CSP_ENFORCE === "true";
  const cspHeader = enforceCsp
    ? "Content-Security-Policy"
    : "Content-Security-Policy-Report-Only";

  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set(cspHeader, policy);

  const response = (() => {
    const isProtected = protectedPrefixes.some(
      (prefix) =>
        request.nextUrl.pathname === prefix ||
        request.nextUrl.pathname.startsWith(`${prefix}/`),
    );
    const cookieName =
      process.env.CUSTOMER_SESSION_COOKIE_NAME ?? "vfbiz_customer_session";

    if (isProtected && !request.cookies.has(cookieName)) {
      const login = new URL("/api/auth/login", request.url);
      login.searchParams.set("returnTo", request.nextUrl.pathname);
      return NextResponse.redirect(login);
    }

    return NextResponse.next({ request: { headers: requestHeaders } });
  })();

  response.headers.set(cspHeader, policy);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|bff|_next/static|_next/image|icon.svg).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
