import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import {
  WorkforceAuthorizationConflictError,
  WorkforceAuthorizationValidationError,
} from '../errors/workforce-authorization.errors';
import { WorkforceAuthorizationRepository } from '../ports/workforce-authorization.repository';
import { WorkforceAuthorizationService } from './workforce-authorization.service';

const principal: AccessPrincipal = {
  audience: ['vfbiz-api'],
  authenticatedAt: new Date('2026-07-24T04:00:00.000Z'),
  authenticationContext: null,
  authenticationMethods: ['pwd', 'otp'],
  authorizedParty: 'vfbiz-workforce-portal',
  issuer: 'https://identity.example/realms/vfbiz-workforce',
  realm: 'workforce',
  scopes: ['openid'],
  sessionId: 'session-1',
  subject: 'workforce-user-1',
};

function repository(
  overrides: Partial<WorkforceAuthorizationRepository> = {},
): WorkforceAuthorizationRepository {
  return {
    getRole: jest.fn(),
    isRoleAssignedToPrincipal: jest.fn(),
    listCapabilities: jest.fn(),
    ...overrides,
  } as unknown as WorkforceAuthorizationRepository;
}

describe('WorkforceAuthorizationService', () => {
  it('blocks capability expansion on a role assigned to the actor', async () => {
    const port = repository({
      getRole: jest.fn().mockResolvedValue({
        capabilityKeys: ['authorization.role.read'],
        id: 'role-1',
      }),
      isRoleAssignedToPrincipal: jest.fn().mockResolvedValue(true),
      listCapabilities: jest.fn().mockResolvedValue([
        {
          deprecated: false,
          key: 'authorization.role.read',
          riskTier: 'sensitive',
        },
        {
          deprecated: false,
          key: 'audit.event.read',
          riskTier: 'sensitive',
        },
      ]),
    });
    const service = new WorkforceAuthorizationService(port);

    await expect(
      service.replaceRoleCapabilities(principal, {
        capabilityKeys: ['authorization.role.read', 'audit.event.read'],
        correlationId: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
        expectedVersion: 1,
        roleId: 'role-1',
      }),
    ).rejects.toBeInstanceOf(WorkforceAuthorizationConflictError);
  });

  it('requires maker-checker for any privileged role change', async () => {
    const port = repository({
      getRole: jest.fn().mockResolvedValue({
        capabilityKeys: ['authorization.role.read'],
        id: 'role-1',
      }),
      isRoleAssignedToPrincipal: jest.fn().mockResolvedValue(false),
      listCapabilities: jest.fn().mockResolvedValue([
        {
          deprecated: false,
          key: 'authorization.role.read',
          riskTier: 'sensitive',
        },
        {
          deprecated: false,
          key: 'authorization.role.update',
          riskTier: 'privileged',
        },
      ]),
    });
    const service = new WorkforceAuthorizationService(port);

    await expect(
      service.replaceRoleCapabilities(principal, {
        capabilityKeys: [
          'authorization.role.read',
          'authorization.role.update',
        ],
        correlationId: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
        expectedVersion: 1,
        roleId: 'role-1',
      }),
    ).rejects.toBeInstanceOf(WorkforceAuthorizationConflictError);
  });

  it('rejects an organizational scope outside the closed catalog', async () => {
    const service = new WorkforceAuthorizationService(repository());

    await expect(
      service.createAssignment(principal, {
        correlationId: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
        effectiveAt: new Date('2026-07-24T04:00:00.000Z'),
        expiresAt: null,
        identitySubjectId: 'subject-2',
        reason: 'Synthetic authorization test.',
        roleId: 'role-1',
        scopes: [
          {
            type: 'region' as 'global',
            ref: 'north',
          },
        ],
      }),
    ).rejects.toBeInstanceOf(WorkforceAuthorizationValidationError);
  });

  it('routes privileged assignment through an approved change request', async () => {
    const port = repository({
      getRole: jest.fn().mockResolvedValue({
        capabilityKeys: ['authorization.assignment.create'],
        id: 'role-1',
      }),
      listCapabilities: jest.fn().mockResolvedValue([
        {
          deprecated: false,
          key: 'authorization.assignment.create',
          riskTier: 'privileged',
        },
      ]),
    });
    const service = new WorkforceAuthorizationService(port);

    await expect(
      service.createAssignment(principal, {
        correlationId: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
        effectiveAt: new Date('2026-07-24T04:00:00.000Z'),
        expiresAt: new Date('2026-07-25T04:00:00.000Z'),
        identitySubjectId: 'subject-2',
        reason: 'Synthetic authorization test.',
        roleId: 'role-1',
        scopes: [{ type: 'global', ref: 'global' }],
      }),
    ).rejects.toBeInstanceOf(WorkforceAuthorizationConflictError);
  });

  it('rejects a privileged request with a mismatched target type', () => {
    const service = new WorkforceAuthorizationService(repository());

    expect(() =>
      service.createChangeRequest(principal, {
        correlationId: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
        payload: {},
        reason: 'Synthetic authorization test.',
        requestType: 'create-privileged-assignment',
        riskTier: 'privileged',
        targetRef: 'subject-2',
        targetType: 'workforce-role',
      }),
    ).toThrow(WorkforceAuthorizationValidationError);
  });
});
