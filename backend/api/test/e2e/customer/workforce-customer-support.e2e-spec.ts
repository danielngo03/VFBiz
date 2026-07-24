import { Test } from '@nestjs/testing';
import {
  FastifyAdapter,
  type NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from '../../../src/app.module';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import { AuthorizationDecisionService } from '../../../src/modules/access/application/services/authorization-decision.service';
import { WorkforceCustomerSupportRepository } from '../../../src/modules/customer/application/ports/workforce-customer-support.repository';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';
import { LocalSessionStatusVerifier } from '../../../src/platform/security/local-session-status.verifier';
import { OidcTokenVerifier } from '../../../src/platform/security/oidc-token.verifier';
import { WorkforceEntitlementReader } from '../../../src/platform/security/workforce-entitlement-reader';

function workforcePrincipal(
  overrides: Partial<AccessPrincipal> = {},
): AccessPrincipal {
  return {
    authenticatedAt: new Date(),
    authenticationContext: 'urn:vfbiz:loa:2',
    authenticationMethods: ['pwd', 'otp'],
    audience: ['vfbiz-workforce-api'],
    authorizedParty: 'vfbiz-workforce-bff',
    emailVerified: true,
    issuer: 'https://id.example/realms/workforce',
    realm: 'workforce',
    scopes: [],
    sessionId: 'workforce-session-1',
    subject: 'support-agent-1',
    ...overrides,
  };
}

async function applicationFor(input: {
  readonly allowed?: boolean;
  readonly principal?: AccessPrincipal;
  readonly search?: jest.Mock;
}) {
  const principal = input.principal ?? workforcePrincipal();
  const entitlements = {
    capabilities: [
      {
        key: 'customer-support.customer.read',
        riskTier: 'sensitive' as const,
        scopes: [{ ref: 'VN', type: 'market' as const }],
      },
    ],
    identitySubjectId: '00000000-0000-4000-a000-000000000001',
    revision: '12',
  };
  const authorization = {
    decide: jest.fn().mockResolvedValue({
      allowed: input.allowed ?? true,
      code:
        (input.allowed ?? true) === true
          ? 'ALLOWED'
          : 'INSUFFICIENT_CAPABILITY',
      revision: '12',
    }),
    getEntitlements: jest.fn().mockResolvedValue(entitlements),
  };
  const search =
    input.search ??
    jest.fn().mockResolvedValue([
      {
        displayName: 'Nguyen Van A',
        garageVehicleCount: 1,
        id: '00000000-0000-4000-a000-000000000010',
        locale: 'vi-VN',
        market: 'VN',
        status: 'active',
        updatedAt: new Date('2026-07-24T08:00:00Z'),
      },
    ]);
  const moduleFixture = await Test.createTestingModule({
    imports: [AppModule],
  })
    .overrideProvider(OidcTokenVerifier)
    .useValue({ verify: jest.fn().mockResolvedValue(principal) })
    .overrideProvider(LocalSessionStatusVerifier)
    .useValue({ isDenied: jest.fn().mockResolvedValue(false) })
    .overrideProvider(AuthorizationDecisionService)
    .useValue(authorization)
    .overrideProvider(WorkforceEntitlementReader)
    .useValue(authorization)
    .overrideProvider(WorkforceCustomerSupportRepository)
    .useValue({ search })
    .compile();
  const app = moduleFixture.createNestApplication<NestFastifyApplication>(
    new FastifyAdapter(),
  );
  await configureApplication(app);
  await app.init();
  await app.getHttpAdapter().getInstance().ready();
  return { app, authorization, search };
}

describe('Workforce customer support boundary (e2e)', () => {
  it('returns a minimized market-scoped projection with an audited reason', async () => {
    const { app, search } = await applicationFor({});
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'x-access-reason': 'Resolve verified customer support case',
      },
      method: 'GET',
      url: '/api/v1/workforce/customer-support/customers?query=Nguyen&limit=20',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual([
      expect.objectContaining({
        displayName: 'Nguyen Van A',
        garageVehicleCount: 1,
        market: 'VN',
      }),
    ]);
    expect(response.body).not.toContain('email');
    expect(response.body).not.toContain('phone');
    expect(search).toHaveBeenCalledWith(
      expect.objectContaining({
        allowedMarkets: ['VN'],
        reason: 'Resolve verified customer support case',
      }),
    );
    await app.close();
  });

  it('requires either OTP or WebAuthn evidence before authorization/data access', async () => {
    const { app, search } = await applicationFor({
      principal: workforcePrincipal({ authenticationMethods: ['pwd'] }),
    });
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'x-access-reason': 'Resolve verified customer support case',
      },
      method: 'GET',
      url: '/api/v1/workforce/customer-support/customers?query=Nguyen',
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({
      code: 'STEP_UP_AUTHENTICATION_REQUIRED',
    });
    expect(search).not.toHaveBeenCalled();
    await app.close();
  });

  it('accepts WebAuthn as an alternative MFA method', async () => {
    const { app } = await applicationFor({
      principal: workforcePrincipal({
        authenticationMethods: ['pwd', 'webauthn'],
      }),
    });
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'x-access-reason': 'Resolve verified customer support case',
      },
      method: 'GET',
      url: '/api/v1/workforce/customer-support/customers?query=Nguyen',
    });

    expect(response.statusCode).toBe(200);
    await app.close();
  });

  it('denies missing capability before customer data access', async () => {
    const { app, search } = await applicationFor({ allowed: false });
    const response = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'x-access-reason': 'Resolve verified customer support case',
      },
      method: 'GET',
      url: '/api/v1/workforce/customer-support/customers?query=Nguyen',
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({
      code: 'INSUFFICIENT_CAPABILITY',
    });
    expect(search).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects broad queries and missing business reason', async () => {
    const { app, search } = await applicationFor({});
    const broad = await app.inject({
      headers: {
        authorization: 'Bearer header.payload.signature',
        'x-access-reason': 'Resolve verified customer support case',
      },
      method: 'GET',
      url: '/api/v1/workforce/customer-support/customers?query=a',
    });
    const noReason = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/workforce/customer-support/customers?query=Nguyen',
    });

    expect(broad.statusCode).toBe(400);
    expect(broad.json()).toMatchObject({
      code: 'CUSTOMER_SEARCH_QUERY_INVALID',
    });
    expect(noReason.statusCode).toBe(400);
    expect(noReason.json()).toMatchObject({
      code: 'CUSTOMER_ACCESS_REASON_REQUIRED',
    });
    expect(search).not.toHaveBeenCalled();
    await app.close();
  });
});
