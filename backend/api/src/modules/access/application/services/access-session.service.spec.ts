import type {
  AccessPrincipal,
  VerifiedAccessPrincipal,
} from '../../../../platform/security/access-principal';
import {
  MissingSessionReferenceError,
  type AccessSessionView,
} from '../../domain/access-session';
import { AccessSessionRepository } from '../ports/access-session.repository';
import { CiamSessionRevocationPort } from '../ports/ciam-session-revocation.port';
import { AccessSessionService } from './access-session.service';

const principal: AccessPrincipal = {
  authenticationContext: null,
  authenticationMethods: [],
  audience: ['vfbiz-customer-api'],
  authorizedParty: 'vfbiz-customer-bff',
  issuer: 'https://id.example/realms/customer',
  realm: 'customer',
  scopes: ['session:read', 'session:revoke'],
  sessionId: 'opaque-session',
  subject: 'customer-1',
};
const session: AccessSessionView = {
  authenticatedAt: new Date('2026-07-23T08:00:00Z'),
  deviceLabel: 'Safari on iPhone',
  emailVerified: true,
  expiresAt: new Date('2026-07-24T08:00:00Z'),
  id: '49028ab3-a07c-4b82-8527-ae494828206a',
  isCurrent: true,
  lastSeenAt: new Date('2026-07-23T09:00:00Z'),
  mfaSatisfied: true,
  networkHint: '203.0.113.0/24',
  revokedAt: new Date('2026-07-23T10:00:00Z'),
  status: 'revoked',
  userAgentSummary: 'Mobile Safari',
};

describe('AccessSessionService', () => {
  it('maps verified temporal claims into one session observation', async () => {
    const reconcile = jest.fn().mockResolvedValue(session);
    const repository = { reconcile } as unknown as AccessSessionRepository;
    const service = new AccessSessionService(repository, {
      revoke: jest.fn(),
      revokeAll: jest.fn(),
      securityStatus: jest.fn(),
    });
    const verified: VerifiedAccessPrincipal = {
      ...principal,
      authenticatedAt: new Date('2026-07-23T08:00:00Z'),
      expiresAt: new Date('2026-07-23T09:00:00Z'),
      issuedAt: new Date('2026-07-23T08:15:00Z'),
      emailVerified: true,
    };
    const observedAt = new Date('2026-07-23T08:20:00Z');

    await service.observeVerifiedPrincipal(
      verified,
      {
        deviceLabel: 'Safari on iPhone',
        ipPrefix: '203.0.113.0/24',
        userAgentSummary: 'Mobile Safari',
      },
      observedAt,
    );

    expect(reconcile).toHaveBeenCalledWith(
      expect.objectContaining({
        authenticatedAt: verified.authenticatedAt,
        eventRevision: 1784798984794500000n,
        expiresAt: verified.expiresAt,
        emailVerified: true,
        ipPrefix: '203.0.113.0/24',
        lastSeenAt: observedAt,
        mfaSatisfied: false,
        providerSessionSecretReference: null,
        sessionReference: verified.sessionId,
        userAgentSummary: 'Mobile Safari',
      }),
      observedAt,
    );
  });

  it('fails closed when the verified token has no session reference', () => {
    const service = new AccessSessionService(
      { reconcile: jest.fn() } as unknown as AccessSessionRepository,
      {
        revoke: jest.fn(),
        revokeAll: jest.fn(),
        securityStatus: jest.fn(),
      },
    );
    const verified: VerifiedAccessPrincipal = {
      ...principal,
      authenticatedAt: new Date('2026-07-23T08:00:00Z'),
      expiresAt: new Date('2026-07-23T09:00:00Z'),
      issuedAt: new Date('2026-07-23T08:15:00Z'),
      sessionId: null,
    };

    expect(() => service.observeVerifiedPrincipal(verified)).toThrow(
      MissingSessionReferenceError,
    );
  });

  it('keeps local revocation fail-closed when CIAM is unavailable', async () => {
    const completeRevocation = jest.fn();
    const repository = {
      beginRevocation: jest.fn().mockResolvedValue({
        dispatch: true,
        providerRoute: 'customer-ciam',
        providerSessionSecretReference: 'secret://ciam/session/1',
        reconciliation: 'pending',
        revocationVersion: 1,
        session,
      }),
      completeRevocation,
    } as unknown as AccessSessionRepository;
    const ciam = {
      revoke: jest.fn().mockRejectedValue(new Error('provider unavailable')),
    } as unknown as CiamSessionRevocationPort;

    await expect(
      new AccessSessionService(repository, ciam).revoke(principal, session.id),
    ).resolves.toEqual({
      reconciliation: 'retry_required',
      session,
    });
    expect(completeRevocation).toHaveBeenCalledWith(
      session.id,
      1,
      'retry_required',
      expect.any(Date),
    );
  });

  it('does not call CIAM when no provider reference is available', async () => {
    const repository = {
      beginRevocation: jest.fn().mockResolvedValue({
        dispatch: false,
        providerRoute: null,
        providerSessionSecretReference: null,
        reconciliation: 'manual_review_required',
        revocationVersion: 1,
        session,
      }),
    } as unknown as AccessSessionRepository;
    const revoke = jest.fn();
    const ciam = { revoke } as unknown as CiamSessionRevocationPort;

    await expect(
      new AccessSessionService(repository, ciam).revoke(principal, session.id),
    ).resolves.toEqual({
      reconciliation: 'manual_review_required',
      session,
    });
    expect(revoke).not.toHaveBeenCalled();
  });
});
