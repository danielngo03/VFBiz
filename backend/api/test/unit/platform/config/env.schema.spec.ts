import { validateEnvironment } from '../../../../src/platform/config/env.schema';

const validEnvironment = {
  NODE_ENV: 'development',
  VFBIZ_API_HOST: '127.0.0.1',
  VFBIZ_API_PORT: '8000',
  VFBIZ_DATABASE_URL: 'postgresql://vfbiz:vfbiz@127.0.0.1:5432/vfbiz',
  VFBIZ_REDIS_URL: 'redis://127.0.0.1:6379/1',
  VFBIZ_CUSTOMER_OIDC_ISSUER: 'http://127.0.0.1:8080/realms/vfbiz-customer',
  VFBIZ_CUSTOMER_OIDC_JWKS_URI:
    'http://127.0.0.1:8080/realms/vfbiz-customer/protocol/openid-connect/certs',
  VFBIZ_CUSTOMER_OIDC_AUDIENCE: 'vfbiz-customer-api',
  VFBIZ_CUSTOMER_OIDC_AUTHORIZED_PARTIES: 'vfbiz-customer-bff,vfbiz-mobile',
  VFBIZ_WORKFORCE_OIDC_ISSUER: 'http://127.0.0.1:8080/realms/vfbiz-workforce',
  VFBIZ_WORKFORCE_OIDC_JWKS_URI:
    'http://127.0.0.1:8080/realms/vfbiz-workforce/protocol/openid-connect/certs',
  VFBIZ_WORKFORCE_OIDC_AUDIENCE: 'vfbiz-workforce-api',
  VFBIZ_WORKFORCE_OIDC_AUTHORIZED_PARTIES: 'vfbiz-workforce-bff',
} as const;

describe('validateEnvironment', () => {
  it('returns converted and validated values', () => {
    const result = validateEnvironment(validEnvironment);

    expect(result.VFBIZ_API_PORT).toBe(8000);
    expect(result.VFBIZ_API_DOCS_ENABLED).toBe(true);
    expect(result.VFBIZ_WORKFORCE_API_DOCS_ENABLED).toBe(true);
    expect(result.VFBIZ_API_TRUSTED_PROXY_CIDRS).toBe('');
  });

  it('disables interactive API docs by default outside development', () => {
    const result = validateEnvironment({
      ...validEnvironment,
      NODE_ENV: 'staging',
    });

    expect(result.VFBIZ_API_DOCS_ENABLED).toBe(false);
    expect(result.VFBIZ_WORKFORCE_API_DOCS_ENABLED).toBe(false);
  });

  it('allows API docs to be enabled explicitly outside development', () => {
    const result = validateEnvironment({
      ...validEnvironment,
      NODE_ENV: 'staging',
      VFBIZ_API_DOCS_ENABLED: 'true',
    });

    expect(result.VFBIZ_API_DOCS_ENABLED).toBe(true);
  });

  it('refuses to expose workforce API documentation in production', () => {
    expect(() =>
      validateEnvironment({
        ...validEnvironment,
        NODE_ENV: 'production',
        VFBIZ_WORKFORCE_API_DOCS_ENABLED: 'true',
        VFBIZ_CUSTOMER_OIDC_ISSUER:
          'https://identity.example/realms/vfbiz-customer',
        VFBIZ_CUSTOMER_OIDC_JWKS_URI:
          'https://identity.example/realms/vfbiz-customer/protocol/openid-connect/certs',
        VFBIZ_WORKFORCE_OIDC_ISSUER:
          'https://identity.example/realms/vfbiz-workforce',
        VFBIZ_WORKFORCE_OIDC_JWKS_URI:
          'https://identity.example/realms/vfbiz-workforce/protocol/openid-connect/certs',
      }),
    ).toThrow(/workforce API documentation must be disabled in production/);
  });

  it('rejects invalid ports', () => {
    expect(() =>
      validateEnvironment({ ...validEnvironment, VFBIZ_API_PORT: '70000' }),
    ).toThrow(/VFBIZ_API_PORT/);
  });

  it('accepts an explicit proxy CIDR allowlist', () => {
    const result = validateEnvironment({
      ...validEnvironment,
      VFBIZ_API_TRUSTED_PROXY_CIDRS:
        '10.20.0.0/16,192.168.100.10/32,2001:db8:42::/48',
    });

    expect(result.VFBIZ_API_TRUSTED_PROXY_CIDRS).toBe(
      '10.20.0.0/16,192.168.100.10/32,2001:db8:42::/48',
    );
  });

  it.each(['*', '0.0.0.0/0', '::/0', 'proxy.internal', '10.0.0.1'])(
    'rejects unsafe trusted proxy value %s',
    (value) => {
      expect(() =>
        validateEnvironment({
          ...validEnvironment,
          VFBIZ_API_TRUSTED_PROXY_CIDRS: value,
        }),
      ).toThrow(/VFBIZ_API_TRUSTED_PROXY_CIDRS/);
    },
  );

  it('requires HTTPS OIDC trust endpoints in production', () => {
    expect(() =>
      validateEnvironment({
        ...validEnvironment,
        NODE_ENV: 'production',
      }),
    ).toThrow(/OIDC issuer and JWKS URIs/);
  });

  it('rejects a shared issuer or audience across customer and workforce', () => {
    expect(() =>
      validateEnvironment({
        ...validEnvironment,
        VFBIZ_WORKFORCE_OIDC_ISSUER:
          validEnvironment.VFBIZ_CUSTOMER_OIDC_ISSUER,
      }),
    ).toThrow(/issuers must be distinct/);
    expect(() =>
      validateEnvironment({
        ...validEnvironment,
        VFBIZ_WORKFORCE_OIDC_AUDIENCE:
          validEnvironment.VFBIZ_CUSTOMER_OIDC_AUDIENCE,
      }),
    ).toThrow(/audiences must be distinct/);
  });
});
