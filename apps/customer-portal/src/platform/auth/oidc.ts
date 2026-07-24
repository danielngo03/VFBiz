import "server-only";
import { createHash } from "node:crypto";
import { createRemoteJWKSet, jwtVerify } from "jose";
import { z } from "zod";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";

const tokenSchema = z.object({
  access_token: z.string().min(1),
  expires_in: z.number().int().positive(),
  id_token: z.string().min(1).optional(),
  refresh_token: z.string().min(1).optional(),
});

function endpoint(path: string): URL {
  const { CUSTOMER_OIDC_ISSUER } = readCustomerPortalEnvironment();
  return new URL(
    `${CUSTOMER_OIDC_ISSUER.replace(/\/$/u, "")}/protocol/openid-connect/${path}`,
  );
}

export function authorizationUrl(input: {
  readonly codeVerifier: string;
  readonly mode?: "configure-mfa" | "login" | "register";
  readonly nonce: string;
  readonly state: string;
}): URL {
  const environment = readCustomerPortalEnvironment();
  const url = endpoint(input.mode === "register" ? "registrations" : "auth");
  url.search = new URLSearchParams({
    client_id: environment.CUSTOMER_OIDC_CLIENT_ID,
    code_challenge: createHash("sha256")
      .update(input.codeVerifier)
      .digest("base64url"),
    code_challenge_method: "S256",
    nonce: input.nonce,
    redirect_uri: environment.CUSTOMER_OIDC_REDIRECT_URI,
    response_type: "code",
    scope:
      "openid profile email profile:read profile:write consent:read consent:write session:read session:revoke garage:read garage:write data-request:create data-request:read",
    state: input.state,
  }).toString();
  if (input.mode === "configure-mfa") {
    url.searchParams.set("kc_action", "CONFIGURE_TOTP");
  }
  return url;
}

export function passwordResetUrl(): URL {
  const environment = readCustomerPortalEnvironment();
  const url = new URL(
    `${environment.CUSTOMER_OIDC_ISSUER.replace(/\/$/u, "")}/login-actions/reset-credentials`,
  );
  url.search = new URLSearchParams({
    client_id: environment.CUSTOMER_OIDC_CLIENT_ID,
    redirect_uri: new URL(
      "/",
      environment.CUSTOMER_OIDC_REDIRECT_URI,
    ).toString(),
  }).toString();
  return url;
}

async function tokenRequest(body: URLSearchParams) {
  const environment = readCustomerPortalEnvironment();
  body.set("client_id", environment.CUSTOMER_OIDC_CLIENT_ID);
  body.set("client_secret", environment.CUSTOMER_OIDC_CLIENT_SECRET);
  const response = await fetch(endpoint("token"), {
    body,
    cache: "no-store",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    method: "POST",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error("Customer OIDC token request failed.");
  return tokenSchema.parse(await response.json());
}

export async function exchangeCode(code: string, codeVerifier: string) {
  const environment = readCustomerPortalEnvironment();
  const token = await tokenRequest(
    new URLSearchParams({
      code,
      code_verifier: codeVerifier,
      grant_type: "authorization_code",
      redirect_uri: environment.CUSTOMER_OIDC_REDIRECT_URI,
    }),
  );
  if (token.id_token === undefined)
    throw new Error("Missing customer ID token.");
  return { ...token, id_token: token.id_token };
}

export async function refreshTokens(refreshToken: string) {
  return tokenRequest(
    new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: refreshToken,
    }),
  );
}

export async function revokeToken(refreshToken: string | undefined) {
  if (refreshToken === undefined) return false;
  const environment = readCustomerPortalEnvironment();
  try {
    const response = await fetch(endpoint("logout"), {
      body: new URLSearchParams({
        client_id: environment.CUSTOMER_OIDC_CLIENT_ID,
        client_secret: environment.CUSTOMER_OIDC_CLIENT_SECRET,
        refresh_token: refreshToken,
      }),
      cache: "no-store",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      method: "POST",
      signal: AbortSignal.timeout(5_000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function verifyCustomerIdToken(idToken: string, nonce: string) {
  const environment = readCustomerPortalEnvironment();
  const issuer = environment.CUSTOMER_OIDC_ISSUER.replace(/\/$/u, "");
  const { payload } = await jwtVerify(
    idToken,
    createRemoteJWKSet(new URL(`${issuer}/protocol/openid-connect/certs`)),
    { audience: environment.CUSTOMER_OIDC_CLIENT_ID, issuer },
  );
  const claims = z
    .object({
      amr: z.array(z.string()).optional(),
      auth_time: z.number().int().positive(),
      email_verified: z.literal(true),
      nonce: z.string(),
      sid: z.string().min(1),
      sub: z.string().min(1),
    })
    .parse(payload);
  if (claims.nonce !== nonce) throw new Error("OIDC nonce mismatch.");
  return {
    authenticatedAt: new Date(claims.auth_time * 1_000),
    emailVerified: true as const,
    mfaSatisfied:
      claims.amr?.some((method) =>
        ["otp", "mfa", "webauthn"].includes(method),
      ) ?? false,
    providerSessionId: claims.sid,
    subject: claims.sub,
  };
}

const backchannelLogoutEvent =
  "http://schemas.openid.net/event/backchannel-logout";

export async function verifyBackchannelLogoutToken(logoutToken: string) {
  const environment = readCustomerPortalEnvironment();
  const issuer = environment.CUSTOMER_OIDC_ISSUER.replace(/\/$/u, "");
  const { payload } = await jwtVerify(
    logoutToken,
    createRemoteJWKSet(new URL(`${issuer}/protocol/openid-connect/certs`)),
    {
      audience: environment.CUSTOMER_OIDC_CLIENT_ID,
      issuer,
      requiredClaims: ["events", "iat", "jti"],
    },
  );
  const claims = z
    .object({
      events: z.record(z.string(), z.unknown()),
      iat: z.number().int().positive(),
      jti: z.string().min(1),
      nonce: z.never().optional(),
      sid: z.string().min(1).optional(),
      sub: z.string().min(1).optional(),
    })
    .refine((value) => value.sid !== undefined || value.sub !== undefined)
    .parse(payload);
  const event = claims.events[backchannelLogoutEvent];
  if (
    typeof event !== "object" ||
    event === null ||
    Array.isArray(event) ||
    Object.keys(event).length !== 0
  ) {
    throw new Error("Missing OIDC back-channel logout event.");
  }
  const now = Math.floor(Date.now() / 1_000);
  if (claims.iat < now - 300 || claims.iat > now + 60) {
    throw new Error("Stale OIDC back-channel logout token.");
  }
  return {
    jti: claims.jti,
    providerSessionId: claims.sid,
    subject: claims.sub,
  };
}
