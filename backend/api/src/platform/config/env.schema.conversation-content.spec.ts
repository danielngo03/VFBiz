import { validateEnvironment } from './env.schema';

const validEnvironment = {
  NODE_ENV: 'development',
  VFBIZ_DATABASE_URL: 'postgresql://vfbiz:vfbiz@127.0.0.1:5434/vfbiz',
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
};

describe('conversation content environment', () => {
  it('allows omitted local content protection configuration', () => {
    expect(validateEnvironment(validEnvironment)).toMatchObject({
      NODE_ENV: 'development',
    });
  });

  it('requires both active key id and keyring', () => {
    expect(() =>
      validateEnvironment({
        ...validEnvironment,
        VFBIZ_CONVERSATION_CONTENT_ACTIVE_KEY_ID: 'key-2026-01',
      }),
    ).toThrow(/active key id and keyring must be configured together/);
  });
});
