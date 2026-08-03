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
  VFBIZ_INTERNAL_AI_RESPONSE_VERIFICATION_KEYRING:
    '{"keys":[{"alg":"EdDSA","kid":"ai-response-current","publicKeyFile":"/run/secrets/ai-response-public.pem"}]}',
  VFBIZ_INTERNAL_AI_SUBJECT_PSEUDONYMIZATION_KEY:
    'MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=',
} as const;

const liveControl = {
  VFBIZ_CHAT_LIVE_CONTROL_ID: 'staging-chat-control-01',
  VFBIZ_CHAT_LIVE_CONTROL_AUTHORITY_SHA256: 'a'.repeat(64),
  VFBIZ_CHAT_LIVE_CONTROL_GENERATION: '9',
  VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE: '2026-08-02T00:00:00Z',
  VFBIZ_CHAT_LIVE_CONTROL_EXPIRES_AT: '2026-08-03T00:00:00Z',
  VFBIZ_CHAT_LIVE_CONTROL_RELEASE_ENVELOPE_SHA256: 'c'.repeat(64),
  VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION: '11',
} as const;

const authenticatedStagingEnvironment = {
  ...baseEnvironment,
  ...enabledInternalAi,
  ...liveControl,
  NODE_ENV: 'staging',
  VFBIZ_CUSTOMER_OIDC_ISSUER:
    'https://identity.example.test/realms/vfbiz-customer',
  VFBIZ_CUSTOMER_OIDC_JWKS_URI:
    'https://identity.example.test/realms/vfbiz-customer/protocol/openid-connect/certs',
  VFBIZ_WORKFORCE_OIDC_ISSUER:
    'https://identity.example.test/realms/vfbiz-workforce',
  VFBIZ_WORKFORCE_OIDC_JWKS_URI:
    'https://identity.example.test/realms/vfbiz-workforce/protocol/openid-connect/certs',
  VFBIZ_INTERNAL_AI_BASE_URL: 'https://ai.staging.internal',
  VFBIZ_INTERNAL_AI_ALLOWED_HOSTS: 'ai.staging.internal',
  VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: 'true',
  VFBIZ_CHAT_API_MODE: 'authenticated-staging',
} as const;

describe('internal AI environment validation', () => {
  it('keeps internal AI disabled by default without trust material', () => {
    expect(validateEnvironment(baseEnvironment)).toMatchObject({
      VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: false,
      VFBIZ_INTERNAL_AI_ENABLED: false,
      VFBIZ_CHAT_API_MODE: 'disabled',
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

  it('opens only authenticated staging Chat with enabled dispatch', () => {
    expect(validateEnvironment(authenticatedStagingEnvironment)).toMatchObject({
      VFBIZ_CHAT_API_MODE: 'authenticated-staging',
      VFBIZ_CHAT_LIVE_CONTROL_GENERATION: 9,
    });
    expect(() =>
      validateEnvironment({
        ...baseEnvironment,
        NODE_ENV: 'staging',
        VFBIZ_CHAT_API_MODE: 'authenticated-staging',
      }),
    ).toThrow('requires enabled internal AI dispatch');
    expect(() =>
      validateEnvironment({
        ...baseEnvironment,
        ...enabledInternalAi,
        ...liveControl,
        NODE_ENV: 'development',
        VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: 'true',
        VFBIZ_CHAT_API_MODE: 'authenticated-staging',
      }),
    ).toThrow('permitted only in staging/test');
    expect(() =>
      validateEnvironment({
        ...baseEnvironment,
        ...enabledInternalAi,
        VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: 'true',
        VFBIZ_CHAT_API_MODE: 'public-release',
      }),
    ).toThrow('public Chat release is not available');
  });

  it('requires all live-control values for authenticated staging Chat', () => {
    const withoutLiveControl = Object.fromEntries(
      Object.keys(liveControl).map((key) => [key, undefined]),
    );

    expect(() =>
      validateEnvironment({
        ...authenticatedStagingEnvironment,
        ...withoutLiveControl,
      }),
    ).toThrow(
      'requires complete live-control identity, authority, generation, validity window and release anchor',
    );
  });

  it.each(Object.keys(liveControl))(
    'rejects partial live-control configuration missing %s',
    (missingKey) => {
      expect(() =>
        validateEnvironment({
          ...authenticatedStagingEnvironment,
          [missingKey]: undefined,
        }),
      ).toThrow(
        'requires complete live-control identity, authority, generation, validity window and release anchor',
      );
    },
  );

  it.each([
    [8, 'a'.repeat(8)],
    [128, 'a'.repeat(128)],
  ])(
    'accepts a valid live-control ID at the %i-character boundary',
    (_length, controlId) => {
      expect(
        validateEnvironment({
          ...authenticatedStagingEnvironment,
          VFBIZ_CHAT_LIVE_CONTROL_GENERATION: Number.MAX_SAFE_INTEGER,
          VFBIZ_CHAT_LIVE_CONTROL_ID: controlId,
          VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION:
            Number.MAX_SAFE_INTEGER,
        }),
      ).toMatchObject({
        VFBIZ_CHAT_LIVE_CONTROL_GENERATION: Number.MAX_SAFE_INTEGER,
        VFBIZ_CHAT_LIVE_CONTROL_ID: controlId,
        VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION:
          Number.MAX_SAFE_INTEGER,
      });
    },
  );

  it.each([
    ['short control id', { VFBIZ_CHAT_LIVE_CONTROL_ID: 'short' }],
    [
      'invalid control id character',
      { VFBIZ_CHAT_LIVE_CONTROL_ID: 'staging/chat/control' },
    ],
    [
      'overlong control id',
      { VFBIZ_CHAT_LIVE_CONTROL_ID: `a${'b'.repeat(128)}` },
    ],
    [
      'uppercase authority digest',
      { VFBIZ_CHAT_LIVE_CONTROL_AUTHORITY_SHA256: 'A'.repeat(64) },
    ],
    [
      'short authority digest',
      { VFBIZ_CHAT_LIVE_CONTROL_AUTHORITY_SHA256: 'a'.repeat(63) },
    ],
    [
      'uppercase release envelope digest',
      { VFBIZ_CHAT_LIVE_CONTROL_RELEASE_ENVELOPE_SHA256: 'C'.repeat(64) },
    ],
    [
      'short release envelope digest',
      { VFBIZ_CHAT_LIVE_CONTROL_RELEASE_ENVELOPE_SHA256: 'c'.repeat(63) },
    ],
  ])('rejects malformed live-control %s', (_name, overrides) => {
    expect(() =>
      validateEnvironment({
        ...authenticatedStagingEnvironment,
        ...overrides,
      }),
    ).toThrow('Invalid API environment');
  });

  it.each([0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])(
    'rejects unsafe live-control generation %s',
    (generation) => {
      expect(() =>
        validateEnvironment({
          ...authenticatedStagingEnvironment,
          VFBIZ_CHAT_LIVE_CONTROL_GENERATION: generation,
        }),
      ).toThrow('Invalid API environment');
    },
  );

  it.each([0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])(
    'rejects unsafe release pointer revision %s',
    (revision) => {
      expect(() =>
        validateEnvironment({
          ...authenticatedStagingEnvironment,
          VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION: revision,
        }),
      ).toThrow('Invalid API environment');
    },
  );

  it.each([
    ['fractional seconds', '2026-08-02T00:00:00.000Z'],
    ['UTC offset', '2026-08-02T07:00:00+07:00'],
    ['missing seconds', '2026-08-02T00:00Z'],
    ['impossible calendar date', '2026-02-30T00:00:00Z'],
    ['lowercase UTC marker', '2026-08-02T00:00:00z'],
  ])('rejects %s in live-control timestamps', (_name, timestamp) => {
    expect(() =>
      validateEnvironment({
        ...authenticatedStagingEnvironment,
        VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE: timestamp,
      }),
    ).toThrow('Invalid API environment');
  });

  it.each([
    [
      'equal bounds',
      '2026-08-02T00:00:00Z',
      '2026-08-02T00:00:00Z',
      'not-before must precede expires-at',
    ],
    [
      'reversed bounds',
      '2026-08-02T00:00:01Z',
      '2026-08-02T00:00:00Z',
      'not-before must precede expires-at',
    ],
    [
      'a window over 24 hours',
      '2026-08-02T00:00:00Z',
      '2026-08-03T00:00:01Z',
      'validity window must not exceed 24 hours',
    ],
  ])('rejects %s', (_name, notBefore, expiresAt, expectedMessage) => {
    expect(() =>
      validateEnvironment({
        ...authenticatedStagingEnvironment,
        VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE: notBefore,
        VFBIZ_CHAT_LIVE_CONTROL_EXPIRES_AT: expiresAt,
      }),
    ).toThrow(expectedMessage);
  });

  it.each(['disabled', 'public-release'])(
    'rejects every stray live-control value in %s mode',
    (mode) => {
      for (const [key, value] of Object.entries(liveControl)) {
        expect(() =>
          validateEnvironment({
            ...baseEnvironment,
            VFBIZ_CHAT_API_MODE: mode,
            [key]: value,
          }),
        ).toThrow(
          'live-control values require authenticated staging Chat mode',
        );
      }
    },
  );

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
