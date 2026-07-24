import { Test } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from '../../../src/app.module';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';
import { LocalSessionStatusVerifier } from '../../../src/platform/security/local-session-status.verifier';
import { OidcTokenVerifier } from '../../../src/platform/security/oidc-token.verifier';
import { CustomerAccountRepository } from '../../../src/modules/customer/application/ports/customer-account.repository';
import type { CustomerProfileView } from '../../../src/modules/customer/domain/customer-account';

const profile: CustomerProfileView = {
  communicationPreferences: { email: false, push: false, sms: false },
  displayName: null,
  locale: 'vi',
  market: 'VN',
  timezone: 'Asia/Ho_Chi_Minh',
  updatedAt: new Date('2026-07-23T07:00:00.000Z'),
  version: 1,
};

const ACCOUNT_OPERATION_SCOPES = [
  'profile:read',
  'profile:write',
  'consent:read',
  'consent:write',
  'data-request:create',
  'data-request:read',
] as const;

const principal = (
  realm: 'customer' | 'workforce',
  scopes: readonly string[] = ACCOUNT_OPERATION_SCOPES,
  authorizedParty = `vfbiz-${realm}-bff`,
): AccessPrincipal => ({
  authenticationContext: 'urn:vfbiz:loa:1',
  authenticationMethods: ['pwd'],
  audience: [`vfbiz-${realm}-api`],
  authorizedParty,
  issuer: `https://id.example/realms/${realm}`,
  realm,
  scopes,
  sessionId: 'session-123',
  subject: 'subject-123',
});

function expectScopePolicyHidden(response: {
  readonly body: string;
  readonly statusCode: number;
  json(): unknown;
}): void {
  expect(response.statusCode).toBe(403);
  expect(response.json()).toMatchObject({ code: 'INSUFFICIENT_SCOPE' });
  for (const policyDetail of [
    ...ACCOUNT_OPERATION_SCOPES,
    'vfbiz-customer-bff',
    'vfbiz-mobile',
  ]) {
    expect(response.body).not.toContain(policyDetail);
  }
}

const repository = {
  createDataRequest: jest.fn(),
  getDataRequest: jest.fn(),
  listDataRequests: jest.fn(),
  listCurrentConsents: jest.fn().mockResolvedValue([]),
  provisionProfile: jest.fn().mockResolvedValue(profile),
  recordConsents: jest.fn().mockResolvedValue([]),
  updateProfile: jest
    .fn()
    .mockResolvedValue({ ...profile, displayName: 'Anh Tuấn', version: 2 }),
};

async function applicationFor(
  accessPrincipal: AccessPrincipal,
): Promise<NestFastifyApplication> {
  const moduleFixture = await Test.createTestingModule({
    imports: [AppModule],
  })
    .overrideProvider(OidcTokenVerifier)
    .useValue({ verify: jest.fn().mockResolvedValue(accessPrincipal) })
    .overrideProvider(LocalSessionStatusVerifier)
    .useValue({ isDenied: jest.fn().mockResolvedValue(false) })
    .overrideProvider(CustomerAccountRepository)
    .useValue(repository)
    .compile();

  const application =
    moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );
  await configureApplication(application);
  await application.init();
  await application.getHttpAdapter().getInstance().ready();
  return application;
}

describe('Customer account boundary (e2e)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    repository.listDataRequests.mockResolvedValue([]);
  });

  it('returns a subject-scoped profile with an optimistic ETag', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me',
    });

    expect(response.statusCode).toBe(200);
    expect(response.headers.etag).toBe('"profile-1"');
    expect(response.json()).toMatchObject({
      communicationPreferences: {
        email: false,
        push: false,
        sms: false,
      },
      locale: 'vi',
      market: 'VN',
      version: 1,
    });
    await app.close();
  });

  it('allows the approved mobile client with the correct operation scope', async () => {
    const app = await applicationFor(
      principal('customer', ['profile:read'], 'vfbiz-mobile'),
    );
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me',
    });

    expect(response.statusCode).toBe(200);
    expect(repository.provisionProfile).toHaveBeenCalledTimes(1);
    await app.close();
  });

  it('rejects an unapproved customer client even with the correct scope', async () => {
    const app = await applicationFor(
      principal('customer', ['profile:read'], 'unapproved-customer-client'),
    );
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me',
    });

    expectScopePolicyHidden(response);
    expect(response.body).not.toContain('unapproved-customer-client');
    expect(repository.provisionProfile).not.toHaveBeenCalled();
    await app.close();
  });

  it('requires If-Match for profile mutation', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
      },
      method: 'PATCH',
      payload: { displayName: 'Anh Tuấn' },
      url: '/api/v1/me',
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({
      code: 'PROFILE_IF_MATCH_REQUIRED',
    });
    await app.close();
  });

  it('rejects an empty profile patch without advancing its version', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
        'if-match': '"profile-1"',
      },
      method: 'PATCH',
      payload: {},
      url: '/api/v1/me',
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ code: 'PROFILE_PATCH_EMPTY' });
    expect(repository.updateProfile).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects a valid workforce token at a customer-only route', async () => {
    const app = await applicationFor(principal('workforce'));
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me',
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({ code: 'IDENTITY_REALM_FORBIDDEN' });
    expect(repository.provisionProfile).not.toHaveBeenCalled();
    await app.close();
  });

  it('requires a bounded idempotency key for consent mutation', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
      },
      method: 'PUT',
      payload: {
        consents: [
          {
            policyVersion: 'analytics-2026-07',
            purpose: 'analytics',
            state: 'granted',
          },
        ],
      },
      url: '/api/v1/me/consents',
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ code: 'IDEMPOTENCY_KEY_REQUIRED' });
    await app.close();
  });

  it('rejects duplicate consent purposes before repository persistence', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
        'idempotency-key': 'consent-request-0002',
      },
      method: 'PUT',
      payload: {
        consents: [
          {
            policyVersion: 'analytics-2026-07',
            purpose: 'analytics',
            state: 'granted',
          },
          {
            policyVersion: 'analytics-2026-08',
            purpose: 'analytics',
            state: 'withdrawn',
          },
        ],
      },
      url: '/api/v1/me/consents',
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ code: 'CONSENT_BATCH_INVALID' });
    expect(repository.recordConsents).not.toHaveBeenCalled();
    await app.close();
  });

  it.each([{ scopes: [] }, { scopes: ['consent:read'] }])(
    'rejects profile access with missing or wrong scopes: $scopes',
    async ({ scopes }) => {
      const app = await applicationFor(principal('customer', scopes));
      const response = await app.inject({
        headers: { authorization: 'Bearer header.payload.signature' },
        method: 'GET',
        url: '/api/v1/me',
      });

      expectScopePolicyHidden(response);
      expect(repository.provisionProfile).not.toHaveBeenCalled();
      await app.close();
    },
  );

  it.each([{ scopes: [] }, { scopes: ['profile:read'] }])(
    'rejects consent access with missing or wrong scopes: $scopes',
    async ({ scopes }) => {
      const app = await applicationFor(principal('customer', scopes));
      const response = await app.inject({
        headers: { authorization: 'Bearer header.payload.signature' },
        method: 'GET',
        url: '/api/v1/me/consents',
      });

      expectScopePolicyHidden(response);
      expect(repository.listCurrentConsents).not.toHaveBeenCalled();
      await app.close();
    },
  );

  it.each([{ scopes: [] }, { scopes: ['consent:write'] }])(
    'rejects DSAR creation with missing or wrong scopes: $scopes',
    async ({ scopes }) => {
      const app = await applicationFor(principal('customer', scopes));
      const response = await app.inject({
        headers: {
          authorization: 'Bearer header.payload.signature',
          'content-type': 'application/json',
          'idempotency-key': 'data-request-0001',
        },
        method: 'POST',
        payload: { type: 'export' },
        url: '/api/v1/me/data-requests',
      });

      expectScopePolicyHidden(response);
      expect(repository.createDataRequest).not.toHaveBeenCalled();
      await app.close();
    },
  );

  it('lists only the data requests returned for the verified subject', async () => {
    repository.listDataRequests.mockResolvedValue([
      {
        completedAt: null,
        id: 'caa38420-305d-4cb5-a1e9-cdfdd08ea421',
        requestedAt: new Date('2026-07-23T10:00:00.000Z'),
        status: 'requested',
        type: 'export',
      },
    ]);
    const app = await applicationFor(
      principal('customer', ['data-request:read']),
    );
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me/data-requests',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual([
      expect.objectContaining({
        id: 'caa38420-305d-4cb5-a1e9-cdfdd08ea421',
        status: 'requested',
        type: 'export',
      }),
    ]);
    expect(repository.listDataRequests).toHaveBeenCalledWith(
      expect.objectContaining({ subject: 'subject-123' }),
    );
    await app.close();
  });

  it.each([{ scopes: [] }, { scopes: ['data-request:create'] }])(
    'rejects DSAR reads with missing or wrong scopes: $scopes',
    async ({ scopes }) => {
      const app = await applicationFor(principal('customer', scopes));
      const response = await app.inject({
        headers: { authorization: 'Bearer header.payload.signature' },
        method: 'GET',
        url: '/api/v1/me/data-requests',
      });

      expectScopePolicyHidden(response);
      expect(repository.listDataRequests).not.toHaveBeenCalled();
      await app.close();
    },
  );
});
