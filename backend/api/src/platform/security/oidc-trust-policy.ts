import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { IdentityRealm } from './access-principal';

export interface OidcTrustProfile {
  readonly audience: string;
  readonly authorizedParties: ReadonlySet<string>;
  readonly issuer: string;
  readonly jwksUri: string;
  readonly realm: IdentityRealm;
}

function parseAuthorizedParties(value: string): ReadonlySet<string> {
  return new Set(
    value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

@Injectable()
export class OidcTrustPolicy {
  private readonly profilesByIssuer: ReadonlyMap<string, OidcTrustProfile>;

  constructor(config: ConfigService) {
    const customer = this.profile(config, 'customer');
    const workforce = this.profile(config, 'workforce');
    this.profilesByIssuer = new Map([
      [customer.issuer, customer],
      [workforce.issuer, workforce],
    ]);
  }

  forIssuer(issuer: string): OidcTrustProfile | null {
    return this.profilesByIssuer.get(issuer) ?? null;
  }

  private profile(
    config: ConfigService,
    realm: IdentityRealm,
  ): OidcTrustProfile {
    const prefix = `VFBIZ_${realm.toUpperCase()}_OIDC`;
    return Object.freeze({
      audience: config.getOrThrow<string>(`${prefix}_AUDIENCE`),
      authorizedParties: parseAuthorizedParties(
        config.getOrThrow<string>(`${prefix}_AUTHORIZED_PARTIES`),
      ),
      issuer: config.getOrThrow<string>(`${prefix}_ISSUER`),
      jwksUri: config.getOrThrow<string>(`${prefix}_JWKS_URI`),
      realm,
    });
  }
}
