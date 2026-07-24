import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { exchangeCode, verifyCustomerIdToken } from "@/platform/auth/oidc";
import {
  hardenPrivateResponse,
  privateJson,
} from "@/platform/api/http-responses";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";
import { customerClientContext } from "@/platform/session/client-context";
import { newCsrfToken } from "@/platform/session/request-security";
import {
  consumeAttempt,
  newSessionId,
  writeSession,
} from "@/platform/session/redis-token-vault";

const attemptCookie = "vfbiz_customer_login_attempt";

export async function GET(request: Request) {
  const environment = readCustomerPortalEnvironment();
  const cookieStore = await cookies();
  const attemptId = cookieStore.get(attemptCookie)?.value;
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!attemptId || !code || !state) {
    return privateJson({ error: "invalid_callback" }, { status: 400 });
  }
  const attempt = await consumeAttempt(attemptId);
  if (attempt === null || attempt.state !== state) {
    const response = privateJson(
      { error: "invalid_callback" },
      { status: 400 },
    );
    response.cookies.delete(attemptCookie);
    return response;
  }
  try {
    const token = await exchangeCode(code, attempt.codeVerifier);
    const identity = await verifyCustomerIdToken(token.id_token, attempt.nonce);
    const context = customerClientContext(request);
    const now = new Date();
    const sessionId = newSessionId();
    const revision = await writeSession(
      {
        ...context,
        authenticatedAt: identity.authenticatedAt,
        csrfToken: newCsrfToken(),
        emailVerified: true,
        expiresAt: new Date(
          now.getTime() + environment.CUSTOMER_SESSION_MAX_AGE_SECONDS * 1_000,
        ),
        id: sessionId,
        lastSeenAt: now,
        mfaSatisfied: identity.mfaSatisfied,
        providerSessionId: identity.providerSessionId,
        subject: identity.subject,
      },
      {
        accessToken: token.access_token,
        expiresAt: new Date(now.getTime() + token.expires_in * 1_000),
        ...(token.refresh_token === undefined
          ? {}
          : { refreshToken: token.refresh_token }),
      },
    );
    if (revision === null) throw new Error("Session write was fenced.");
    const response = NextResponse.redirect(
      new URL(attempt.returnTo, request.url),
    );
    response.cookies.delete(attemptCookie);
    response.cookies.set(environment.CUSTOMER_SESSION_COOKIE_NAME, sessionId, {
      httpOnly: true,
      maxAge: environment.CUSTOMER_SESSION_MAX_AGE_SECONDS,
      path: "/",
      sameSite: "lax",
      secure: environment.CUSTOMER_SESSION_COOKIE_SECURE,
    });
    return hardenPrivateResponse(response);
  } catch {
    const response = privateJson(
      { error: "authentication_failed" },
      { status: 403 },
    );
    response.cookies.delete(attemptCookie);
    return response;
  }
}
