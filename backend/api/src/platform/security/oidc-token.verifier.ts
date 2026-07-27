import { Injectable } from '@nestjs/common';
import type { VerifiedAccessPrincipal } from './access-principal';
import { OidcJwksProvider } from './oidc-jwks.provider';
import { OidcTrustPolicy } from './oidc-trust-policy';

const ROLE_PATTERN = /^[a-z][a-z0-9-]{0,79}$/;

function verifiedRealmRoles(claim: unknown): readonly string[] {
  if (claim === undefined) return Object.freeze([]);
  if (
    typeof claim !== 'object' ||
    claim === null ||
    !('roles' in claim) ||
    !Array.isArray(claim.roles) ||
    !claim.roles.every(
      (role): role is string =>
        typeof role === 'string' && ROLE_PATTERN.test(role),
    )
  ) {
    throw new Error('Access token realm roles claim is invalid');
  }
  return Object.freeze([...new Set(claim.roles)]);
}

@Injectable()
export class OidcTokenVerifier {
  constructor(
    private readonly trustPolicy: OidcTrustPolicy,
    private readonly jwks: OidcJwksProvider,
  ) {}

  async verify(token: string): Promise<VerifiedAccessPrincipal> {
    const { decodeJwt, decodeProtectedHeader, jwtVerify } =
      await import('jose');
    const untrustedHeader = decodeProtectedHeader(token);
    const untrustedPayload = decodeJwt(token);
    if (
      (untrustedHeader.typ !== 'at+jwt' && untrustedHeader.typ !== 'JWT') ||
      typeof untrustedPayload.iss !== 'string'
    ) {
      throw new Error('Token is not an accepted access-token profile');
    }
    const profile = this.trustPolicy.forIssuer(untrustedPayload.iss);
    if (profile === null) throw new Error('Token issuer is not trusted');

    const resolver = await this.jwks.resolverFor(profile);
    const { payload } = await jwtVerify(token, resolver, {
      algorithms: ['RS256', 'ES256'],
      audience: profile.audience,
      issuer: profile.issuer,
      requiredClaims: ['exp', 'iat', 'sub', 'iss', 'aud', 'azp'],
    });
    if (
      typeof payload.sub !== 'string' ||
      payload.sub.length === 0 ||
      typeof payload.azp !== 'string' ||
      typeof payload.iat !== 'number' ||
      typeof payload.exp !== 'number' ||
      !profile.authorizedParties.has(payload.azp)
    ) {
      throw new Error(
        'Access token subject, temporal claims or authorized party is invalid',
      );
    }
    const issuedAt = new Date(payload.iat * 1000);
    const expiresAt = new Date(payload.exp * 1000);
    // auth_time reflects the end-user's original authentication moment and
    // must NOT fall back to iat: iat advances on every silent refresh, which
    // would let a stale login satisfy a step-up-MFA freshness check forever.
    // Callers that need a recency signal must treat an absent auth_time as
    // absent, not as "authenticated now".
    const authenticatedAt =
      typeof payload.auth_time === 'number'
        ? new Date(payload.auth_time * 1000)
        : undefined;
    if (
      (authenticatedAt !== undefined &&
        authenticatedAt.getTime() > issuedAt.getTime()) ||
      issuedAt.getTime() >= expiresAt.getTime()
    ) {
      throw new Error('Access token temporal claims are inconsistent');
    }
    const audience = Array.isArray(payload.aud)
      ? payload.aud
      : typeof payload.aud === 'string'
        ? [payload.aud]
        : [];
    const scopes =
      typeof payload.scope === 'string' ? payload.scope.split(' ') : [];
    const authenticationMethods = Array.isArray(payload.amr)
      ? payload.amr.filter(
          (method): method is string => typeof method === 'string',
        )
      : [];
    if (
      payload.email_verified !== undefined &&
      typeof payload.email_verified !== 'boolean'
    ) {
      throw new Error('Access token email_verified claim is invalid');
    }
    return Object.freeze({
      ...(authenticatedAt !== undefined ? { authenticatedAt } : {}),
      authenticationContext:
        typeof payload.acr === 'string' ? payload.acr : null,
      authenticationMethods,
      ...(typeof payload.email_verified === 'boolean'
        ? { emailVerified: payload.email_verified }
        : {}),
      subject: payload.sub,
      issuer: profile.issuer,
      issuedAt,
      expiresAt,
      audience,
      authorizedParty: payload.azp,
      realm: profile.realm,
      roles: verifiedRealmRoles(payload.realm_access),
      scopes,
      sessionId: typeof payload.sid === 'string' ? payload.sid : null,
    });
  }
}
