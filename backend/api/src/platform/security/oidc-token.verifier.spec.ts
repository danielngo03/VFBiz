import { ConfigService } from '@nestjs/config';
import { OidcJwksProvider } from './oidc-jwks.provider';
import { OidcTokenVerifier } from './oidc-token.verifier';
import { OidcTrustPolicy } from './oidc-trust-policy';

const customerIssuer = 'https://id.example/realms/customer';
const workforceIssuer = 'https://id.example/realms/workforce';

function testConfig(): ConfigService {
  return new ConfigService({
    VFBIZ_CUSTOMER_OIDC_AUDIENCE: 'vfbiz-customer-api',
    VFBIZ_CUSTOMER_OIDC_AUTHORIZED_PARTIES: 'vfbiz-customer-bff,vfbiz-mobile',
    VFBIZ_CUSTOMER_OIDC_ISSUER: customerIssuer,
    VFBIZ_CUSTOMER_OIDC_JWKS_URI: `${customerIssuer}/certs`,
    VFBIZ_WORKFORCE_OIDC_AUDIENCE: 'vfbiz-workforce-api',
    VFBIZ_WORKFORCE_OIDC_AUTHORIZED_PARTIES: 'vfbiz-workforce-bff',
    VFBIZ_WORKFORCE_OIDC_ISSUER: workforceIssuer,
    VFBIZ_WORKFORCE_OIDC_JWKS_URI: `${workforceIssuer}/certs`,
  });
}

describe('OidcTokenVerifier', () => {
  async function fixture() {
    const { createLocalJWKSet, exportJWK, generateKeyPair, SignJWT } =
      await import('jose');
    const { privateKey, publicKey } = await generateKeyPair('RS256');
    const publicJwk = await exportJWK(publicKey);
    publicJwk.alg = 'RS256';
    publicJwk.kid = 'test-key';
    publicJwk.use = 'sig';
    const resolver = createLocalJWKSet({ keys: [publicJwk] });
    const jwks = {
      resolverFor: jest.fn().mockResolvedValue(resolver),
    } as unknown as OidcJwksProvider;
    const verifier = new OidcTokenVerifier(
      new OidcTrustPolicy(testConfig()),
      jwks,
    );

    const sign = (overrides: {
      audience?: string;
      authTime?: number;
      authorizedParty?: string;
      issuer?: string;
      realmRoles?: readonly string[];
      type?: string;
    }) =>
      new SignJWT({
        acr: 'urn:vfbiz:loa:2',
        amr: ['pwd', 'otp'],
        auth_time: overrides.authTime,
        azp: overrides.authorizedParty ?? 'vfbiz-customer-bff',
        realm_access:
          overrides.realmRoles === undefined
            ? undefined
            : { roles: overrides.realmRoles },
        scope: 'profile:read profile:write',
        sid: 'session-123',
      })
        .setProtectedHeader({
          alg: 'RS256',
          kid: 'test-key',
          typ: overrides.type ?? 'at+jwt',
        })
        .setIssuer(overrides.issuer ?? customerIssuer)
        .setAudience(overrides.audience ?? 'vfbiz-customer-api')
        .setSubject('customer-123')
        .setIssuedAt()
        .setExpirationTime('5m')
        .sign(privateKey);

    return { sign, verifier };
  }

  it('creates a realm-aware principal from an allowlisted access token', async () => {
    const { sign, verifier } = await fixture();

    const result = await verifier.verify(await sign({}));
    const { expiresAt, issuedAt, ...principal } = result;
    expect(expiresAt).toBeInstanceOf(Date);
    expect(issuedAt).toBeInstanceOf(Date);
    expect(principal).toEqual({
      authenticationContext: 'urn:vfbiz:loa:2',
      authenticationMethods: ['pwd', 'otp'],
      audience: ['vfbiz-customer-api'],
      authorizedParty: 'vfbiz-customer-bff',
      issuer: customerIssuer,
      realm: 'customer',
      roles: [],
      scopes: ['profile:read', 'profile:write'],
      sessionId: 'session-123',
      subject: 'customer-123',
    });
  });

  it('surfaces authenticatedAt from a present auth_time claim', async () => {
    const { sign, verifier } = await fixture();
    const authTime = Math.floor(Date.now() / 1000) - 30;

    const result = await verifier.verify(await sign({ authTime }));

    expect(result.authenticatedAt).toEqual(new Date(authTime * 1000));
  });

  it('does not fabricate authenticatedAt from iat when auth_time is absent', async () => {
    // Regression test: a silently refreshed access token has a fresh `iat`
    // on every refresh even though the user authenticated long ago. Treating
    // a missing auth_time as "authenticated now" would let that refresh
    // permanently satisfy a step-up-MFA freshness check.
    const { sign, verifier } = await fixture();

    const result = await verifier.verify(await sign({}));

    expect(result.authenticatedAt).toBeUndefined();
  });

  it('keeps workforce identity separate from customer identity', async () => {
    const { sign, verifier } = await fixture();

    await expect(
      verifier.verify(
        await sign({
          audience: 'vfbiz-workforce-api',
          authorizedParty: 'vfbiz-workforce-bff',
          issuer: workforceIssuer,
          realmRoles: ['vehicle-data-reviewer'],
        }),
      ),
    ).resolves.toMatchObject({
      authorizedParty: 'vfbiz-workforce-bff',
      issuer: workforceIssuer,
      realm: 'workforce',
      roles: ['vehicle-data-reviewer'],
      subject: 'customer-123',
    });
  });

  it('rejects malformed realm role claims after signature verification', async () => {
    const { sign, verifier } = await fixture();

    await expect(
      verifier.verify(
        await sign({
          audience: 'vfbiz-workforce-api',
          authorizedParty: 'vfbiz-workforce-bff',
          issuer: workforceIssuer,
          realmRoles: ['vehicle-data-reviewer', 'INVALID ROLE'],
        }),
      ),
    ).rejects.toThrow('realm roles claim is invalid');
  });

  it.each([
    {
      name: 'unknown issuer',
      values: { issuer: 'https://attacker.example/realm' },
    },
    {
      name: 'wrong audience',
      values: { audience: 'some-other-api' },
    },
    {
      name: 'unapproved authorized party',
      values: { authorizedParty: 'unknown-client' },
    },
    { name: 'non access-token type', values: { type: 'ID' } },
  ])('rejects $name', async ({ values }) => {
    const { sign, verifier } = await fixture();

    await expect(verifier.verify(await sign(values))).rejects.toThrow();
  });
});
