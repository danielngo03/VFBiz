import { Injectable } from '@nestjs/common';
import type { OidcTrustProfile } from './oidc-trust-policy';

export type JwksResolver = ReturnType<typeof import('jose').createRemoteJWKSet>;

@Injectable()
export class OidcJwksProvider {
  private readonly resolvers = new Map<string, JwksResolver>();

  async resolverFor(profile: OidcTrustProfile): Promise<JwksResolver> {
    const existing = this.resolvers.get(profile.issuer);
    if (existing !== undefined) return existing;

    const { createRemoteJWKSet } = await import('jose');
    const resolver = createRemoteJWKSet(new URL(profile.jwksUri), {
      cooldownDuration: 30_000,
      timeoutDuration: 5_000,
    });
    this.resolvers.set(profile.issuer, resolver);
    return resolver;
  }
}
