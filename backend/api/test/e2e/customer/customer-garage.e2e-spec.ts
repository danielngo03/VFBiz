import { Test } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from '../../../src/app.module';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import { CustomerAccountRepository } from '../../../src/modules/customer/application/ports/customer-account.repository';
import { CustomerGarageRepository } from '../../../src/modules/customer/application/ports/customer-garage.repository';
import type { CreateGarageEntryInput } from '../../../src/modules/customer/application/ports/customer-garage.repository';
import type { CustomerProfileView } from '../../../src/modules/customer/domain/customer-account';
import type { CustomerGarageEntryView } from '../../../src/modules/customer/domain/customer-garage';
import { CheckVehicleVariantEligibilityService } from '../../../src/modules/product';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';
import { LocalSessionStatusVerifier } from '../../../src/platform/security/local-session-status.verifier';
import { OidcTokenVerifier } from '../../../src/platform/security/oidc-token.verifier';

const variantId = '1f7f4e42-7a45-47ce-a798-f0271301fe97';
const entryId = '49028ab3-a07c-4b82-8527-ae494828206a';

const profile: CustomerProfileView = {
  communicationPreferences: { email: false, push: false, sms: false },
  displayName: null,
  locale: 'vi',
  market: 'VN',
  timezone: 'Asia/Ho_Chi_Minh',
  updatedAt: new Date('2026-07-23T08:00:00.000Z'),
  version: 1,
};

const entry: CustomerGarageEntryView = {
  claimedVehicleVariantId: variantId,
  createdAt: new Date('2026-07-23T08:01:00.000Z'),
  id: entryId,
  isPrimary: true,
  nickname: 'Xe gia đình',
  ownershipStatus: 'unverified',
  source: 'self-reported',
  status: 'active',
  updatedAt: new Date('2026-07-23T08:01:00.000Z'),
  version: 1,
};

const GARAGE_OPERATION_SCOPES = ['garage:read', 'garage:write'] as const;

const principal = (
  realm: 'customer' | 'workforce',
  scopes: readonly string[] = GARAGE_OPERATION_SCOPES,
): AccessPrincipal => ({
  authenticationContext: 'urn:vfbiz:loa:1',
  authenticationMethods: ['pwd'],
  audience: [`vfbiz-${realm}-api`],
  authorizedParty: `vfbiz-${realm}-bff`,
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
    ...GARAGE_OPERATION_SCOPES,
    'vfbiz-customer-bff',
    'vfbiz-mobile',
  ]) {
    expect(response.body).not.toContain(policyDetail);
  }
}

const accountRepository = {
  createDataRequest: jest.fn(),
  listCurrentConsents: jest.fn(),
  provisionProfile: jest.fn().mockResolvedValue(profile),
  recordConsents: jest.fn(),
  updateProfile: jest.fn(),
};

const garageRepository = {
  archive: jest.fn().mockResolvedValue({ ...entry, status: 'archived' }),
  create: jest
    .fn<Promise<CustomerGarageEntryView>, [CreateGarageEntryInput]>()
    .mockResolvedValue(entry),
  findCreateReplay: jest.fn().mockResolvedValue(null),
  list: jest.fn().mockResolvedValue([entry]),
  update: jest.fn().mockResolvedValue({ ...entry, version: 2 }),
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
    .useValue(accountRepository)
    .overrideProvider(CustomerGarageRepository)
    .useValue(garageRepository)
    .overrideProvider(CheckVehicleVariantEligibilityService)
    .useValue({ isSelectable: jest.fn().mockResolvedValue(true) })
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

describe('Customer Garage boundary (e2e)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('creates only an unverified entry and returns its ETag', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
        'idempotency-key': 'garage-create-0001',
      },
      method: 'POST',
      payload: {
        claimedVehicleVariantId: variantId,
        isPrimary: true,
        nickname: 'Xe gia đình',
      },
      url: '/api/v1/me/vehicles',
    });

    expect(response.statusCode).toBe(201);
    expect(response.headers.etag).toBe('"garage-1"');
    expect(response.json()).toMatchObject({
      claimedVehicleVariantId: variantId,
      ownershipStatus: 'unverified',
      source: 'self-reported',
    });
    expect(garageRepository.create).toHaveBeenCalledTimes(1);
    expect(garageRepository.create.mock.calls[0]?.[0].principal.subject).toBe(
      'subject-123',
    );
    await app.close();
  });

  it('requires a current ETag for an update', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
      },
      method: 'PATCH',
      payload: { nickname: 'VF 8' },
      url: `/api/v1/me/vehicles/${entryId}`,
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({
      code: 'GARAGE_IF_MATCH_REQUIRED',
    });
    expect(garageRepository.update).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects an empty garage patch without advancing its version', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
        'if-match': '"garage-1"',
      },
      method: 'PATCH',
      payload: {},
      url: `/api/v1/me/vehicles/${entryId}`,
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ code: 'GARAGE_PATCH_EMPTY' });
    expect(garageRepository.update).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects a workforce principal before customer data is read', async () => {
    const app = await applicationFor(principal('workforce'));
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me/vehicles',
    });

    expect(response.statusCode).toBe(403);
    expect(garageRepository.list).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects a non-UUID garage entry identifier', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
        'if-match': '"garage-1"',
      },
      method: 'PATCH',
      payload: { nickname: 'VF 8' },
      url: '/api/v1/me/vehicles/not-an-id',
    });

    expect(response.statusCode).toBe(400);
    expect(garageRepository.update).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects VIN, source and ownership fields from customer input', async () => {
    const app = await applicationFor(principal('customer'));
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'content-type': 'application/json',
        'idempotency-key': 'garage-create-0003',
      },
      method: 'POST',
      payload: {
        claimedVehicleVariantId: variantId,
        ownershipStatus: 'verified',
        source: 'imported',
        vin: 'SYNTHETICVIN00001',
      },
      url: '/api/v1/me/vehicles',
    });

    expect(response.statusCode).toBe(400);
    expect(garageRepository.create).not.toHaveBeenCalled();
    await app.close();
  });

  it.each([{ scopes: [] }, { scopes: ['profile:read'] }])(
    'rejects Garage access with missing or wrong scopes: $scopes',
    async ({ scopes }) => {
      const app = await applicationFor(principal('customer', scopes));
      const response = await app.inject({
        headers: { authorization: 'Bearer header.payload.signature' },
        method: 'GET',
        url: '/api/v1/me/vehicles',
      });

      expectScopePolicyHidden(response);
      expect(garageRepository.list).not.toHaveBeenCalled();
      await app.close();
    },
  );
});
