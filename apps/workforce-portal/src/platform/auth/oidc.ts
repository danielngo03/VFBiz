import 'server-only';
import {createHash} from 'node:crypto';
import {createRemoteJWKSet, jwtVerify} from 'jose';
import {z} from 'zod';
import {readWorkforcePortalEnvironment} from '@/platform/config/environment';

const authorizationTokenResponseSchema = z.object({
  access_token: z.string().min(1),
  refresh_token: z.string().min(1).optional(),
  expires_in: z.number().int().positive(),
  id_token: z.string().min(1),
});

const refreshTokenResponseSchema = z.object({
  access_token: z.string().min(1),
  refresh_token: z.string().min(1).optional(),
  expires_in: z.number().int().positive(),
});

function endpoint(path: string): URL {
  const environment = readWorkforcePortalEnvironment();
  return new URL(
    `${environment.WORKFORCE_OIDC_ISSUER.replace(/\/$/, '')}/protocol/openid-connect/${path}`,
  );
}

export function authorizationUrl(input: {
  state: string;
  nonce: string;
  codeVerifier: string;
}): URL {
  const environment = readWorkforcePortalEnvironment();
  const url = endpoint('auth');
  url.search = new URLSearchParams({
    client_id: environment.WORKFORCE_OIDC_CLIENT_ID,
    code_challenge: createHash('sha256')
      .update(input.codeVerifier)
      .digest('base64url'),
    code_challenge_method: 'S256',
    nonce: input.nonce,
    redirect_uri: environment.WORKFORCE_OIDC_REDIRECT_URI,
    response_type: 'code',
    scope: 'openid profile email',
    state: input.state,
  }).toString();
  return url;
}

export async function exchangeAuthorizationCode(input: {
  code: string;
  codeVerifier: string;
}): Promise<{
  accessToken: string;
  refreshToken?: string;
  idToken: string;
  expiresAt: Date;
}> {
  const environment = readWorkforcePortalEnvironment();
  const response = await fetch(endpoint('token'), {
    body: new URLSearchParams({
      client_id: environment.WORKFORCE_OIDC_CLIENT_ID,
      client_secret: environment.WORKFORCE_OIDC_CLIENT_SECRET,
      code: input.code,
      code_verifier: input.codeVerifier,
      grant_type: 'authorization_code',
      redirect_uri: environment.WORKFORCE_OIDC_REDIRECT_URI,
    }),
    cache: 'no-store',
    headers: {'content-type': 'application/x-www-form-urlencoded'},
    method: 'POST',
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error('OIDC token exchange failed.');
  const token = authorizationTokenResponseSchema.parse(await response.json());
  return {
    accessToken: token.access_token,
    ...(token.refresh_token === undefined
      ? {}
      : {refreshToken: token.refresh_token}),
    idToken: token.id_token,
    expiresAt: new Date(Date.now() + token.expires_in * 1000),
  };
}

export async function refreshAuthorizationTokens(input: {
  refreshToken: string;
}): Promise<{
  accessToken: string;
  refreshToken: string;
  expiresAt: Date;
}> {
  const environment = readWorkforcePortalEnvironment();
  const response = await fetch(endpoint('token'), {
    body: new URLSearchParams({
      client_id: environment.WORKFORCE_OIDC_CLIENT_ID,
      client_secret: environment.WORKFORCE_OIDC_CLIENT_SECRET,
      grant_type: 'refresh_token',
      refresh_token: input.refreshToken,
    }),
    cache: 'no-store',
    headers: {'content-type': 'application/x-www-form-urlencoded'},
    method: 'POST',
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error('OIDC token refresh failed.');
  const token = refreshTokenResponseSchema.parse(await response.json());
  return {
    accessToken: token.access_token,
    refreshToken: token.refresh_token ?? input.refreshToken,
    expiresAt: new Date(Date.now() + token.expires_in * 1000),
  };
}

export async function revokeOidcSession(
  refreshToken: string | undefined,
): Promise<void> {
  if (refreshToken === undefined) return;
  const environment = readWorkforcePortalEnvironment();
  try {
    await fetch(endpoint('logout'), {
      body: new URLSearchParams({
        client_id: environment.WORKFORCE_OIDC_CLIENT_ID,
        client_secret: environment.WORKFORCE_OIDC_CLIENT_SECRET,
        refresh_token: refreshToken,
      }),
      cache: 'no-store',
      headers: {'content-type': 'application/x-www-form-urlencoded'},
      method: 'POST',
      signal: AbortSignal.timeout(5_000),
    });
  } catch {
    // Local session revocation must still complete if the identity provider is down.
  }
}

export async function verifyIdTokenClaims(idToken: string): Promise<{
  emailVerified: boolean;
  subject: string;
  nonce?: string;
  mfaSatisfied: boolean;
}> {
  const environment = readWorkforcePortalEnvironment();
  const issuer = environment.WORKFORCE_OIDC_ISSUER.replace(/\/$/, '');
  const {payload} = await jwtVerify(
    idToken,
    createRemoteJWKSet(new URL(`${issuer}/protocol/openid-connect/certs`)),
    {
      audience: environment.WORKFORCE_OIDC_CLIENT_ID,
      issuer,
    },
  );
  const claims = z
    .object({
      sub: z.string().min(1),
      nonce: z.string().optional(),
      amr: z.array(z.string()).optional(),
      email_verified: z.boolean(),
    })
    .parse(payload);
  return {
    subject: claims.sub,
    emailVerified: claims.email_verified,
    nonce: claims.nonce,
    mfaSatisfied:
      claims.amr?.some((method) =>
        ['otp', 'mfa', 'webauthn'].includes(method),
      ) ?? false,
  };
}
