import type { PrismaService } from '../../../src/platform/database/prisma.service';
import { PrismaAccessSessionRepository } from '../../../src/modules/access/infrastructure/persistence/prisma-access-session.repository';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';

const principal: AccessPrincipal = {
  authenticationContext: null,
  authenticationMethods: [],
  audience: ['vfbiz-customer-api'],
  authorizedParty: 'vfbiz-customer-bff',
  issuer: 'https://id.example/realms/customer',
  realm: 'customer',
  scopes: ['session:read'],
  sessionId: 'opaque-session',
  subject: 'customer-subject',
};
const record = {
  authenticatedAt: new Date('2026-07-23T08:00:00Z'),
  deviceLabel: 'Safari',
  emailVerified: true,
  expiresAt: new Date('2026-07-24T08:00:00Z'),
  id: '49028ab3-a07c-4b82-8527-ae494828206a',
  lastSeenAt: new Date('2026-07-23T09:00:00Z'),
  mfaSatisfied: true,
  observationRevision: 2n,
  providerRoute: 'customer-ciam',
  providerSessionSecretReference: 'secret://ciam/session/1',
  revocationNextRetryAt: null,
  revocationState: 'none',
  revocationVersion: 0,
  revokedAt: null,
  sessionRefHash: 'a'.repeat(64),
  ipPrefix: '203.0.113.0/24',
  userAgentSummary: 'Safari test agent',
};

describe('PrismaAccessSessionRepository contract', () => {
  it('always scopes list queries by verified issuer and subject', async () => {
    const findMany = jest.fn().mockResolvedValue([record]);
    const prisma = {
      sessionProjection: { findMany },
    } as unknown as PrismaService;

    const views = await new PrismaAccessSessionRepository(prisma).list(
      principal,
      new Date('2026-07-23T10:00:00Z'),
    );

    expect(findMany).toHaveBeenCalledWith(
      expect.objectContaining({
        where: {
          identitySubject: {
            issuer: principal.issuer,
            realm: 'customer',
            status: 'active',
            subject: principal.subject,
          },
        },
      }),
    );
    expect(views[0]).not.toHaveProperty('sessionRefHash');
    expect(views[0]).not.toHaveProperty('providerSessionSecretReference');
    expect(views[0]).not.toHaveProperty('ipPrefix');
  });

  it('never reactivates a revoked projection from an out-of-order observation', async () => {
    const revoked = {
      ...record,
      revokedAt: new Date('2026-07-23T09:30:00Z'),
    };
    const updateMany = jest.fn();
    const transaction = {
      identitySubject: {
        upsert: jest.fn().mockResolvedValue({
          id: 'identity-1',
          realm: 'customer',
          status: 'active',
        }),
      },
      sessionProjection: {
        findUnique: jest.fn().mockResolvedValue(revoked),
        updateMany,
      },
    };
    type TransactionCallback = (value: typeof transaction) => Promise<unknown>;
    const prisma = {
      $transaction: jest.fn((callback: TransactionCallback) =>
        callback(transaction),
      ),
    } as unknown as PrismaService;
    const repository = new PrismaAccessSessionRepository(prisma);

    const view = await repository.reconcile(
      {
        authenticatedAt: new Date('2026-07-23T08:00:00Z'),
        authorizedParty: principal.authorizedParty,
        deviceLabel: 'New label from stale event',
        emailVerified: true,
        expiresAt: new Date('2026-07-25T08:00:00Z'),
        issuer: principal.issuer,
        ipPrefix: '203.0.113.0/24',
        lastSeenAt: new Date('2026-07-23T08:30:00Z'),
        mfaSatisfied: true,
        eventRevision: 1n,
        observedAt: new Date('2026-07-23T08:30:00Z'),
        providerRoute: 'customer-ciam',
        providerSessionSecretReference: 'secret://ciam/session/stale',
        realm: 'customer',
        revokedAt: null,
        sessionReference: 'opaque-session',
        subject: principal.subject,
        userAgentSummary: 'Safari test agent',
      },
      new Date('2026-07-23T10:00:00Z'),
    );

    expect(view.status).toBe('revoked');
    expect(updateMany).not.toHaveBeenCalled();
  });

  it('never extends an already-expired projection from a late observation', async () => {
    const expired = {
      ...record,
      expiresAt: new Date('2026-07-23T09:30:00Z'),
    };
    const updateMany = jest.fn();
    const transaction = {
      identitySubject: {
        upsert: jest.fn().mockResolvedValue({
          id: 'identity-1',
          realm: 'customer',
          status: 'active',
        }),
      },
      sessionProjection: {
        findUnique: jest.fn().mockResolvedValue(expired),
        updateMany,
      },
    };
    type TransactionCallback = (value: typeof transaction) => Promise<unknown>;
    const prisma = {
      $transaction: jest.fn((callback: TransactionCallback) =>
        callback(transaction),
      ),
    } as unknown as PrismaService;
    const repository = new PrismaAccessSessionRepository(prisma);

    const view = await repository.reconcile(
      {
        authenticatedAt: new Date('2026-07-23T08:00:00Z'),
        authorizedParty: principal.authorizedParty,
        deviceLabel: 'Late event',
        emailVerified: true,
        expiresAt: new Date('2026-07-25T08:00:00Z'),
        issuer: principal.issuer,
        ipPrefix: '203.0.113.0/24',
        lastSeenAt: new Date('2026-07-23T09:20:00Z'),
        mfaSatisfied: true,
        eventRevision: 3n,
        observedAt: new Date('2026-07-23T09:20:00Z'),
        providerRoute: 'customer-ciam',
        providerSessionSecretReference: null,
        realm: 'customer',
        revokedAt: null,
        sessionReference: 'opaque-session',
        subject: principal.subject,
        userAgentSummary: 'Safari test agent',
      },
      new Date('2026-07-23T10:00:00Z'),
    );

    expect(view.status).toBe('expired');
    expect(updateMany).not.toHaveBeenCalled();
  });
});
