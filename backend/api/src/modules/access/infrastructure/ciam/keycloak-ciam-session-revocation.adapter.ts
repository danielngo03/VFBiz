import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import {
  CiamSessionRevocationPort,
  type CiamIdentitySecurityStatus,
  type CiamSessionRevocationCommand,
  type CiamSessionRevocationOutcome,
  type CiamSubjectCommand,
} from '../../application/ports/ciam-session-revocation.port';

const PROVIDER_TIMEOUT_MS = 5_000;

interface KeycloakUser {
  readonly emailVerified?: unknown;
}

@Injectable()
export class KeycloakCiamSessionRevocationAdapter extends CiamSessionRevocationPort {
  constructor(private readonly config: ConfigService) {
    super();
  }

  revoke(
    command: CiamSessionRevocationCommand,
  ): Promise<'manual_review_required'> {
    // The projection intentionally stores no raw provider session identifier.
    // Per-session provider revocation remains unavailable until a KMS-backed
    // secret-reference resolver is introduced.
    void command;
    return Promise.resolve('manual_review_required');
  }

  async revokeAll(
    command: CiamSubjectCommand,
  ): Promise<CiamSessionRevocationOutcome> {
    const accessToken = await this.adminAccessToken(command.issuer);
    if (accessToken === null) return 'manual_review_required';
    try {
      const response = await fetch(
        `${this.adminBase(command.issuer)}/users/${encodeURIComponent(command.subject)}/logout`,
        {
          headers: { authorization: `Bearer ${accessToken}` },
          method: 'POST',
          signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
        },
      );
      if (response.status === 204) return 'confirmed';
      return response.status >= 500
        ? 'retry_required'
        : 'manual_review_required';
    } catch {
      return 'retry_required';
    }
  }

  async securityStatus(
    command: CiamSubjectCommand,
  ): Promise<CiamIdentitySecurityStatus | null> {
    const accessToken = await this.adminAccessToken(command.issuer);
    if (accessToken === null) return null;
    try {
      const headers = { authorization: `Bearer ${accessToken}` };
      const base = `${this.adminBase(command.issuer)}/users/${encodeURIComponent(command.subject)}`;
      const [userResponse, credentialsResponse] = await Promise.all([
        fetch(base, {
          headers,
          signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
        }),
        fetch(`${base}/credentials`, {
          headers,
          signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
        }),
      ]);
      if (!userResponse.ok || !credentialsResponse.ok) return null;
      const user = (await userResponse.json()) as KeycloakUser;
      const credentials: unknown = await credentialsResponse.json();
      if (
        typeof user.emailVerified !== 'boolean' ||
        !Array.isArray(credentials)
      ) {
        return null;
      }
      return {
        emailVerified: user.emailVerified,
        mfaConfigured: credentials.some(
          (credential: unknown) =>
            typeof credential === 'object' &&
            credential !== null &&
            'type' in credential &&
            (credential as { readonly type?: unknown }).type === 'otp',
        ),
      };
    } catch {
      return null;
    }
  }

  private async adminAccessToken(issuer: string): Promise<string | null> {
    const clientId = this.config.get<string>(
      'VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_ID',
    );
    const clientSecret = this.config.get<string>(
      'VFBIZ_CUSTOMER_CIAM_ADMIN_CLIENT_SECRET',
    );
    if (!clientId || !clientSecret) return null;
    try {
      const body = new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        grant_type: 'client_credentials',
      });
      const response = await fetch(
        `${issuer.replace(/\/$/, '')}/protocol/openid-connect/token`,
        {
          body,
          headers: { 'content-type': 'application/x-www-form-urlencoded' },
          method: 'POST',
          signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
        },
      );
      if (!response.ok) return null;
      const payload = (await response.json()) as { access_token?: unknown };
      return typeof payload.access_token === 'string'
        ? payload.access_token
        : null;
    } catch {
      return null;
    }
  }

  private adminBase(issuer: string): string {
    const parsed = new URL(issuer);
    const marker = '/realms/';
    const index = parsed.pathname.lastIndexOf(marker);
    if (index < 0) throw new Error('Keycloak issuer path is invalid');
    const realm = parsed.pathname.slice(index + marker.length);
    return `${parsed.origin}${parsed.pathname.slice(0, index)}/admin/realms/${encodeURIComponent(realm)}`;
  }
}
