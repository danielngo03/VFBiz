import "server-only";
import { NextResponse } from "next/server";
import { hardenPrivateResponse } from "@/platform/api/http-responses";
import { authorizationUrl } from "./oidc";
import { customerReturnToOrDefault } from "@/platform/auth/safe-return-to";
import { readCustomerPortalEnvironment } from "../config/environment";
import { newAttempt, saveAttempt } from "../session/redis-token-vault";

const attemptCookie = "vfbiz_customer_login_attempt";

type CustomerAuthorizationMode = "configure-mfa" | "login" | "register";

function safeReturnTo(request: Request): string {
  const requested = new URL(request.url).searchParams.get("returnTo");
  return customerReturnToOrDefault(requested);
}

export async function startCustomerAuthorization(
  request: Request,
  mode: CustomerAuthorizationMode,
): Promise<NextResponse> {
  const attempt = newAttempt();
  await saveAttempt(attempt.attemptId, {
    codeVerifier: attempt.codeVerifier,
    nonce: attempt.nonce,
    returnTo: safeReturnTo(request),
    state: attempt.state,
  });
  const response = NextResponse.redirect(
    authorizationUrl({ ...attempt, mode }),
  );
  const environment = readCustomerPortalEnvironment();
  response.cookies.set(attemptCookie, attempt.attemptId, {
    httpOnly: true,
    maxAge: 600,
    path: "/",
    sameSite: "lax",
    secure: environment.CUSTOMER_SESSION_COOKIE_SECURE,
  });
  return hardenPrivateResponse(response);
}
