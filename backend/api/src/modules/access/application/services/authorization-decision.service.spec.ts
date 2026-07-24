import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { WorkforceAuthorizationRepository } from '../ports/workforce-authorization.repository';
import { AuthorizationDecisionService } from './authorization-decision.service';

const principal: AccessPrincipal = {
  audience: ['vfbiz-api'],
  authenticationContext: null,
  authenticationMethods: ['pwd'],
  authorizedParty: 'vfbiz-workforce-portal',
  issuer: 'https://identity.example/realms/vfbiz-workforce',
  realm: 'workforce',
  scopes: ['openid'],
  sessionId: 'session-1',
  subject: 'worker-1',
};

describe('AuthorizationDecisionService', () => {
  it('denies an identity that is not registered locally', async () => {
    const repository = {
      resolveEntitlements: jest.fn().mockResolvedValue(null),
    } as unknown as WorkforceAuthorizationRepository;
    const service = new AuthorizationDecisionService(repository);

    await expect(
      service.decide(principal, {
        mode: 'all-of',
        capabilities: ['authorization.role.read'],
      }),
    ).resolves.toMatchObject({
      allowed: false,
      code: 'IDENTITY_NOT_REGISTERED',
    });
  });

  it('applies capability and organizational scope together', async () => {
    const repository = {
      resolveEntitlements: jest.fn().mockResolvedValue({
        identitySubjectId: 'bd409c14-299f-46cd-9ff4-d8b271842cd9',
        revision: '3',
        capabilities: [
          {
            key: 'customer-support.case.read',
            riskTier: 'sensitive',
            scopes: [{ type: 'showroom', ref: 'showroom-hanoi' }],
          },
        ],
      }),
    } as unknown as WorkforceAuthorizationRepository;
    const service = new AuthorizationDecisionService(repository);

    await expect(
      service.decide(
        principal,
        {
          mode: 'all-of',
          capabilities: ['customer-support.case.read'],
        },
        { type: 'showroom', ref: 'showroom-hcm' },
      ),
    ).resolves.toMatchObject({
      allowed: false,
      code: 'INSUFFICIENT_CAPABILITY',
    });
  });

  it('requires step-up authentication for privileged capabilities', async () => {
    const repository = {
      resolveEntitlements: jest.fn().mockResolvedValue({
        identitySubjectId: 'bd409c14-299f-46cd-9ff4-d8b271842cd9',
        revision: '4',
        capabilities: [
          {
            key: 'authorization.role.update',
            riskTier: 'privileged',
            scopes: [{ type: 'global', ref: 'global' }],
          },
        ],
      }),
    } as unknown as WorkforceAuthorizationRepository;
    const service = new AuthorizationDecisionService(repository);

    await expect(
      service.decide(principal, {
        mode: 'all-of',
        capabilities: ['authorization.role.update'],
      }),
    ).resolves.toMatchObject({
      allowed: false,
      code: 'STEP_UP_AUTHENTICATION_REQUIRED',
    });
  });

  it('accepts privileged capability only when MFA authentication is recent', async () => {
    const repository = {
      resolveEntitlements: jest.fn().mockResolvedValue({
        identitySubjectId: 'bd409c14-299f-46cd-9ff4-d8b271842cd9',
        revision: '5',
        capabilities: [
          {
            key: 'authorization.approval.approve',
            riskTier: 'privileged',
            scopes: [{ type: 'global', ref: 'global' }],
          },
        ],
      }),
    } as unknown as WorkforceAuthorizationRepository;
    const service = new AuthorizationDecisionService(repository);
    const now = new Date('2026-07-24T04:00:00.000Z');

    await expect(
      service.decide(
        {
          ...principal,
          authenticatedAt: new Date('2026-07-24T03:58:00.000Z'),
          authenticationMethods: ['pwd', 'otp'],
        },
        {
          mode: 'all-of',
          capabilities: ['authorization.approval.approve'],
        },
        undefined,
        now,
      ),
    ).resolves.toMatchObject({ allowed: true, code: 'ALLOWED' });
  });
});
