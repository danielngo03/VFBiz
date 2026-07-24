import { Test } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from '../../../src/app.module';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import { AccessSessionRepository } from '../../../src/modules/access/application/ports/access-session.repository';
import { CiamSessionRevocationPort } from '../../../src/modules/access/application/ports/ciam-session-revocation.port';
import {
  AccessSessionNotFoundError,
  type AccessSessionView,
} from '../../../src/modules/access/domain/access-session';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';
import { OidcTokenVerifier } from '../../../src/platform/security/oidc-token.verifier';
import { LocalSessionStatusVerifier } from '../../../src/platform/security/local-session-status.verifier';

const sessionId = '49028ab3-a07c-4b82-8527-ae494828206a';
const session: AccessSessionView = {
  authenticatedAt: new Date('2026-07-23T08:00:00Z'),
  deviceLabel: 'Safari on iPhone',
  emailVerified: true,
  expiresAt: new Date('2026-07-24T08:00:00Z'),
  id: sessionId,
  isCurrent: true,
  lastSeenAt: new Date('2026-07-23T09:00:00Z'),
  mfaSatisfied: true,
  networkHint: '203.0.113.0/24',
  revokedAt: null,
  status: 'active',
  userAgentSummary: 'Mobile Safari',
};

function principal(
  scopes: readonly string[],
  overrides: Partial<AccessPrincipal> = {},
): AccessPrincipal {
  return {
    authenticationContext: 'urn:vfbiz:loa:1',
    authenticationMethods: ['pwd'],
    audience: ['vfbiz-customer-api'],
    authorizedParty: 'vfbiz-customer-bff',
    issuer: 'https://id.example/realms/customer',
    realm: 'customer',
    scopes,
    sessionId: 'opaque-current-session',
    subject: 'customer-subject-1',
    ...overrides,
  };
}

const repository = {
  beginRevocation: jest.fn().mockResolvedValue({
    dispatch: false,
    providerRoute: null,
    providerSessionSecretReference: null,
    reconciliation: 'manual_review_required',
    revocationVersion: 1,
    session: { ...session, revokedAt: new Date(), status: 'revoked' },
  }),
  completeRevocation: jest.fn(),
  list: jest.fn().mockResolvedValue([session]),
  reconcile: jest.fn(),
  revokeAll: jest.fn().mockResolvedValue(2),
  revokeCurrent: jest.fn(),
};
const ciam = {
  revoke: jest.fn(),
  revokeAll: jest.fn().mockResolvedValue('confirmed'),
  securityStatus: jest.fn().mockResolvedValue({
    emailVerified: true,
    mfaConfigured: true,
  }),
};

async function applicationFor(
  accessPrincipal: AccessPrincipal,
  localSessions: Pick<LocalSessionStatusVerifier, 'isDenied'> = {
    isDenied: jest.fn().mockResolvedValue(false),
  },
): Promise<NestFastifyApplication> {
  const moduleFixture = await Test.createTestingModule({
    imports: [AppModule],
  })
    .overrideProvider(OidcTokenVerifier)
    .useValue({ verify: jest.fn().mockResolvedValue(accessPrincipal) })
    .overrideProvider(LocalSessionStatusVerifier)
    .useValue(localSessions)
    .overrideProvider(AccessSessionRepository)
    .useValue(repository)
    .overrideProvider(CiamSessionRevocationPort)
    .useValue(ciam)
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

describe('Access session boundary (e2e)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('lists only through the verified subject and exposes no secret handle', async () => {
    const accessPrincipal = principal(['session:read']);
    const app = await applicationFor(accessPrincipal);
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me/sessions',
    });

    expect(response.statusCode).toBe(200);
    expect(repository.list).toHaveBeenCalledWith(
      expect.objectContaining({
        issuer: accessPrincipal.issuer,
        subject: accessPrincipal.subject,
      }),
      expect.any(Date),
    );
    expect(response.body).not.toContain('opaque-current-session');
    expect(response.body).not.toContain('providerSession');
    expect(response.body).not.toContain('ipPrefix');
    await app.close();
  });

  it('rejects a wrong operation scope before repository access', async () => {
    const app = await applicationFor(principal(['profile:read']));
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me/sessions',
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({ code: 'INSUFFICIENT_SCOPE' });
    expect(repository.list).not.toHaveBeenCalled();
    await app.close();
  });

  it('returns provider-backed identity security without exposing credentials', async () => {
    const accessPrincipal = principal(['session:read'], {
      authenticationMethods: ['pwd', 'webauthn'],
      emailVerified: true,
    });
    const app = await applicationFor(accessPrincipal);
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me/sessions/security',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
      currentSessionMfaSatisfied: true,
      emailVerified: true,
      mfaConfigured: true,
      providerStatus: 'available',
    });
    expect(ciam.securityStatus).toHaveBeenCalledWith({
      issuer: accessPrincipal.issuer,
      subject: accessPrincipal.subject,
    });
    expect(response.body).not.toContain('credential');
    expect(response.body).not.toContain('token');
    await app.close();
  });

  it('denies every local session before requesting subject-wide CIAM logout', async () => {
    const accessPrincipal = principal(['session:revoke']);
    const app = await applicationFor(accessPrincipal);
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'DELETE',
      url: '/api/v1/me/sessions',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({
      locallyRevokedCount: 2,
      reconciliation: 'confirmed',
    });
    expect(repository.revokeAll).toHaveBeenCalledWith(
      expect.objectContaining({ subject: accessPrincipal.subject }),
      expect.any(Date),
    );
    expect(ciam.revokeAll).toHaveBeenCalledWith({
      issuer: accessPrincipal.issuer,
      subject: accessPrincipal.subject,
    });
    await app.close();
  });

  it('rejects the correct scope when the authorized party is not allowed', async () => {
    const app = await applicationFor(
      principal(['session:read'], { authorizedParty: 'untrusted-client' }),
    );
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me/sessions',
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({ code: 'INSUFFICIENT_SCOPE' });
    expect(repository.list).not.toHaveBeenCalled();
    await app.close();
  });

  it('rejects a workforce principal at the customer boundary', async () => {
    const app = await applicationFor(
      principal(['session:read'], {
        issuer: 'https://id.example/realms/workforce',
        realm: 'workforce',
      }),
    );
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me/sessions',
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({ code: 'IDENTITY_REALM_FORBIDDEN' });
    expect(repository.list).not.toHaveBeenCalled();
    await app.close();
  });

  it('does not reveal a session owned by another subject', async () => {
    repository.beginRevocation.mockRejectedValueOnce(
      new AccessSessionNotFoundError(),
    );
    const app = await applicationFor(principal(['session:revoke']));
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'DELETE',
      url: `/api/v1/me/sessions/${sessionId}`,
    });

    expect(response.statusCode).toBe(404);
    expect(response.json()).toMatchObject({ code: 'SESSION_NOT_FOUND' });
    await app.close();
  });

  it('revokes locally and reports manual review when CIAM is disabled', async () => {
    const app = await applicationFor(principal(['session:revoke']));
    const response = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'DELETE',
      url: `/api/v1/me/sessions/${sessionId}`,
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({
      reconciliation: 'manual_review_required',
      session: { id: sessionId, status: 'revoked' },
    });
    expect(ciam.revoke).not.toHaveBeenCalled();
    await app.close();
  });

  it('does not dispatch a second CIAM call for a duplicate revocation', async () => {
    repository.beginRevocation
      .mockResolvedValueOnce({
        dispatch: true,
        providerRoute: 'customer-ciam',
        providerSessionSecretReference: 'secret://ciam/session/1',
        reconciliation: 'pending',
        revocationVersion: 2,
        session: { ...session, revokedAt: new Date(), status: 'revoked' },
      })
      .mockResolvedValueOnce({
        dispatch: false,
        providerRoute: null,
        providerSessionSecretReference: null,
        reconciliation: 'confirmed',
        revocationVersion: 2,
        session: { ...session, revokedAt: new Date(), status: 'revoked' },
      });
    ciam.revoke.mockResolvedValueOnce('confirmed');
    const app = await applicationFor(principal(['session:revoke']));

    const first = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'DELETE',
      url: `/api/v1/me/sessions/${sessionId}`,
    });
    const duplicate = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'DELETE',
      url: `/api/v1/me/sessions/${sessionId}`,
    });

    expect(first.statusCode).toBe(200);
    expect(duplicate.statusCode).toBe(200);
    expect(ciam.revoke).toHaveBeenCalledTimes(1);
    await app.close();
  });

  it('denies subsequent authenticated requests after local revocation', async () => {
    let denied = false;
    const localSessions = {
      isDenied: jest.fn().mockImplementation(() => Promise.resolve(denied)),
    };
    repository.beginRevocation.mockImplementationOnce(() => {
      denied = true;
      return Promise.resolve({
        dispatch: false,
        providerRoute: null,
        providerSessionSecretReference: null,
        reconciliation: 'manual_review_required',
        revocationVersion: 1,
        session: { ...session, revokedAt: new Date(), status: 'revoked' },
      });
    });
    const app = await applicationFor(
      principal(['session:read', 'session:revoke']),
      localSessions,
    );

    const revoked = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'DELETE',
      url: `/api/v1/me/sessions/${sessionId}`,
    });
    const deniedRequest = await app.inject({
      headers: { authorization: 'Bearer header.payload.signature' },
      method: 'GET',
      url: '/api/v1/me/sessions',
    });

    expect(revoked.statusCode).toBe(200);
    expect(deniedRequest.statusCode).toBe(401);
    expect(repository.list).not.toHaveBeenCalled();
    await app.close();
  });
});
