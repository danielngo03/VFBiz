import { validateEnvironment } from './env.schema';

const baseEnvironment = {
  NODE_ENV: 'test',
  VFBIZ_API_HOST: '127.0.0.1',
  VFBIZ_API_PORT: 8000,
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
} as const;

const enabledInternalAi = {
  VFBIZ_INTERNAL_AI_ENABLED: 'true',
  VFBIZ_INTERNAL_AI_BASE_URL: 'http://127.0.0.1:8888',
  VFBIZ_INTERNAL_AI_ALLOWED_HOSTS: '127.0.0.1',
  VFBIZ_INTERNAL_AI_ASSERTION_ACTIVE_KEY_ID: 'api-ai-current',
  VFBIZ_INTERNAL_AI_ASSERTION_KEYRING:
    '{"keys":[{"alg":"ES256","kid":"api-ai-current","privateKeyFile":"/run/secrets/api-ai.pem"}]}',
  VFBIZ_INTERNAL_AI_SUBJECT_PSEUDONYMIZATION_KEY:
    'MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=',
} as const;

describe('internal AI environment validation', () => {
  it('keeps internal AI disabled by default without trust material', () => {
    expect(validateEnvironment(baseEnvironment)).toMatchObject({
      VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: false,
      VFBIZ_INTERNAL_AI_ENABLED: false,
      VFBIZ_INTERNAL_AI_ASSERTION_AUDIENCE: 'vfbiz-ai',
      VFBIZ_INTERNAL_AI_ASSERTION_ISSUER: 'vfbiz-api',
      VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS: 30,
    });
  });

  it('does not allow dispatch without the trust boundary', () => {
    expect(() =>
      validateEnvironment({
        ...baseEnvironment,
        VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: 'true',
      }),
    ).toThrow('internal AI dispatch requires internal AI trust');
  });

  it('accepts an exact loopback origin only in test/development', () => {
    expect(
      validateEnvironment({ ...baseEnvironment, ...enabledInternalAi }),
    ).toMatchObject({
      VFBIZ_INTERNAL_AI_BASE_URL: 'http://127.0.0.1:8888',
      VFBIZ_INTERNAL_AI_REQUEST_TIMEOUT_MS: 15_000,
      VFBIZ_INTERNAL_AI_RETRY_BUDGET: 1,
    });
  });

  it.each([
    {
      name: 'partial trust config',
      overrides: {
        VFBIZ_INTERNAL_AI_ENABLED: 'true',
        VFBIZ_INTERNAL_AI_BASE_URL: 'http://127.0.0.1:8888',
      },
    },
    {
      name: 'trust values while disabled',
      overrides: {
        VFBIZ_INTERNAL_AI_BASE_URL: 'http://127.0.0.1:8888',
      },
    },
    {
      name: 'host outside exact allowlist',
      overrides: {
        ...enabledInternalAi,
        VFBIZ_INTERNAL_AI_BASE_URL: 'http://ai.internal:8888',
      },
    },
    {
      name: 'URL path',
      overrides: {
        ...enabledInternalAi,
        VFBIZ_INTERNAL_AI_BASE_URL: 'http://127.0.0.1:8888/internal',
      },
    },
    {
      name: 'excessive assertion TTL',
      overrides: {
        ...enabledInternalAi,
        VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS: 61,
      },
    },
  ])('rejects $name', ({ overrides }) => {
    expect(() =>
      validateEnvironment({ ...baseEnvironment, ...overrides }),
    ).toThrow('Invalid API environment');
  });

  it('requires HTTPS and rejects loopback in staging', () => {
    expect(() =>
      validateEnvironment({
        ...baseEnvironment,
        ...enabledInternalAi,
        NODE_ENV: 'staging',
      }),
    ).toThrow('must use HTTPS in staging and production');
  });
});
