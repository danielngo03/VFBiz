import { Test } from '@nestjs/testing';
import {
  FastifyAdapter,
  type NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from '../../../src/app.module';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import { CatalogReleaseWorkflowService } from '../../../src/modules/product/application/services/catalog-release-workflow.service';
import { CommercialReleaseWorkflowService } from '../../../src/modules/product/application/services/commercial-release-workflow.service';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';
import { LocalSessionStatusVerifier } from '../../../src/platform/security/local-session-status.verifier';
import { OidcTokenVerifier } from '../../../src/platform/security/oidc-token.verifier';

const releaseId = '5904ad2a-ed10-4e7c-a2b7-3363db999914';

function principal(
  realm: 'customer' | 'workforce',
  roles: readonly string[],
  authenticationMethods: readonly string[],
): AccessPrincipal {
  return {
    authenticationContext: null,
    authenticationMethods,
    audience: [`vfbiz-${realm}-api`],
    authorizedParty: `vfbiz-${realm}-bff`,
    issuer: `https://id.example/realms/${realm}`,
    realm,
    roles,
    scopes: [],
    sessionId: 'session-1',
    subject: `${realm}-subject-1`,
  };
}

describe('Operations release authorization boundary (e2e)', () => {
  let app: NestFastifyApplication;
  const catalog = {
    activate: jest.fn(),
    approve: jest.fn().mockResolvedValue({
      id: releaseId,
      revision: 1,
      state: 'approved',
    }),
    rollback: jest.fn(),
  };
  const commercial = {
    activate: jest.fn(),
    approve: jest.fn(),
    rollback: jest.fn(),
  };
  const principalsByToken = new Map<string, AccessPrincipal>([
    ['customer.token.sig', principal('customer', [], ['pwd', 'otp'])],
    [
      'operator.token.sig',
      principal('workforce', ['vehicle-data-operator'], ['pwd', 'otp']),
    ],
    [
      'password.token.sig',
      principal('workforce', ['vehicle-data-reviewer'], ['pwd']),
    ],
    [
      'reviewer.token.sig',
      principal('workforce', ['vehicle-data-reviewer'], ['pwd', 'otp']),
    ],
  ]);

  beforeAll(async () => {
    const moduleFixture = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(OidcTokenVerifier)
      .useValue({
        verify: jest.fn((token: string) => {
          const observed = principalsByToken.get(token);
          if (observed === undefined) throw new Error('unknown test token');
          return Promise.resolve(observed);
        }),
      })
      .overrideProvider(LocalSessionStatusVerifier)
      .useValue({ isDenied: jest.fn().mockResolvedValue(false) })
      .overrideProvider(CatalogReleaseWorkflowService)
      .useValue(catalog)
      .overrideProvider(CommercialReleaseWorkflowService)
      .useValue(commercial)
      .compile();
    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );
    await configureApplication(app);
    await app.init();
    await app.getHttpAdapter().getInstance().ready();
  });

  afterAll(async () => app.close());

  it.each([
    ['customer.token.sig', 403],
    ['operator.token.sig', 403],
    ['password.token.sig', 403],
  ])('rejects token %s', async (token, expectedStatus) => {
    const response = await app.inject({
      headers: { authorization: `Bearer ${token}` },
      method: 'POST',
      payload: {
        evidenceRef: 'evidence://review/catalog-release',
        expectedRevision: 0,
      },
      url: `/api/v1/operations/releases/vehicle-catalog/${releaseId}/approve`,
    });

    expect(response.statusCode).toBe(expectedStatus);
  });

  it('derives the reviewer from the verified workforce subject', async () => {
    const response = await app.inject({
      headers: {
        authorization: 'Bearer reviewer.token.sig',
        'x-correlation-id': '589c0f85-f4e4-49a5-aea0-fb0d0d91de79',
      },
      method: 'POST',
      payload: {
        evidenceRef: 'evidence://review/catalog-release',
        expectedRevision: 0,
      },
      url: `/api/v1/operations/releases/vehicle-catalog/${releaseId}/approve`,
    });

    expect(response.statusCode).toBe(201);
    expect(catalog.approve).toHaveBeenCalledWith(
      expect.objectContaining({
        correlationId: '589c0f85-f4e4-49a5-aea0-fb0d0d91de79',
        releaseId,
        reviewerRef: 'workforce-subject-1',
      }),
    );
  });
});
