import { Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import {
  isScopeValid,
  principalReference,
  type AuthorizationScope,
} from '../../domain/workforce-authorization';
import {
  WorkforceAuthorizationConflictError,
  WorkforceAuthorizationValidationError,
} from '../errors/workforce-authorization.errors';
import {
  WorkforceAuthorizationRepository,
  type CreateChangeRequestCommand,
} from '../ports/workforce-authorization.repository';

const ROLE_KEY_PATTERN = /^[a-z][a-z0-9-]{0,79}$/;
const PRIVILEGED_REQUEST_TTL_MS = 24 * 60 * 60 * 1000;

@Injectable()
export class WorkforceAuthorizationService {
  constructor(private readonly repository: WorkforceAuthorizationRepository) {}

  entitlements(principal: AccessPrincipal) {
    return this.repository.resolveEntitlements(principal, new Date());
  }

  capabilities() {
    return this.repository.listCapabilities();
  }

  roles() {
    return this.repository.listRoles();
  }

  role(roleId: string) {
    return this.repository.getRole(roleId);
  }

  directorySubjects() {
    return this.repository.listDirectorySubjects();
  }

  organizationUnits() {
    return this.repository.listOrganizationUnits();
  }

  auditEvents() {
    return this.repository.listAuditEvents();
  }

  createRole(
    principal: AccessPrincipal,
    input: {
      key: string;
      displayName: string;
      description?: string;
      correlationId: string;
    },
  ) {
    if (!ROLE_KEY_PATTERN.test(input.key)) {
      throw new WorkforceAuthorizationValidationError('Invalid role key.');
    }
    return this.repository.createRole({
      ...input,
      actorRef: principalReference(principal),
    });
  }

  updateRole(
    principal: AccessPrincipal,
    input: {
      roleId: string;
      expectedVersion: number;
      displayName?: string;
      description?: string | null;
      correlationId: string;
    },
  ) {
    return this.repository.updateRole({
      ...input,
      actorRef: principalReference(principal),
    });
  }

  async replaceRoleCapabilities(
    principal: AccessPrincipal,
    input: {
      roleId: string;
      expectedVersion: number;
      capabilityKeys: readonly string[];
      correlationId: string;
    },
  ) {
    const definitions = await this.repository.listCapabilities();
    const known = new Map(
      definitions.map((definition) => [definition.key, definition]),
    );
    if (
      input.capabilityKeys.some(
        (key) => known.get(key) === undefined || known.get(key)?.deprecated,
      )
    ) {
      throw new WorkforceAuthorizationValidationError(
        'Role contains an unknown or deprecated capability.',
      );
    }
    const current = await this.repository.getRole(input.roleId);
    if (current === null) return null;
    const additions = input.capabilityKeys.filter(
      (key) => !current.capabilityKeys.includes(key),
    );
    if (
      additions.length > 0 &&
      (await this.repository.isRoleAssignedToPrincipal(
        input.roleId,
        principal,
        new Date(),
      ))
    ) {
      throw new WorkforceAuthorizationConflictError(
        'A workforce user cannot expand a role currently assigned to themselves.',
      );
    }
    const changedKeys = new Set([
      ...current.capabilityKeys,
      ...input.capabilityKeys,
    ]);
    if (
      [...changedKeys].some((key) => known.get(key)?.riskTier === 'privileged')
    ) {
      throw new WorkforceAuthorizationConflictError(
        'Privileged role changes require an approved change request.',
      );
    }
    return this.repository.replaceRoleCapabilities({
      ...input,
      actorRef: principalReference(principal),
    });
  }

  assignments() {
    return this.repository.listAssignments();
  }

  async createAssignment(
    principal: AccessPrincipal,
    input: {
      identitySubjectId: string;
      roleId: string;
      effectiveAt: Date;
      expiresAt: Date | null;
      reason: string;
      scopes: readonly AuthorizationScope[];
      correlationId: string;
    },
  ) {
    if (
      input.scopes.length === 0 ||
      input.scopes.some((scope) => !isScopeValid(scope))
    ) {
      throw new WorkforceAuthorizationValidationError(
        'Every assignment requires at least one valid scope.',
      );
    }
    const role = await this.repository.getRole(input.roleId);
    if (role === null) return null;
    const definitions = new Map(
      (await this.repository.listCapabilities()).map((item) => [
        item.key,
        item,
      ]),
    );
    if (
      role.capabilityKeys.some(
        (key) => definitions.get(key)?.riskTier === 'privileged',
      )
    ) {
      throw new WorkforceAuthorizationConflictError(
        'Privileged assignments require an approved change request.',
      );
    }
    return this.repository.createAssignment({
      ...input,
      actorRef: principalReference(principal),
    });
  }

  revokeAssignment(
    principal: AccessPrincipal,
    input: {
      assignmentId: string;
      expectedVersion: number;
      correlationId: string;
    },
  ) {
    return this.repository.revokeAssignment(
      input.assignmentId,
      input.expectedVersion,
      principalReference(principal),
      input.correlationId,
    );
  }

  changeRequests() {
    return this.repository.listChangeRequests();
  }

  createChangeRequest(
    principal: AccessPrincipal,
    input: Omit<CreateChangeRequestCommand, 'requesterRef' | 'expiresAt'>,
  ) {
    if (input.riskTier === 'privileged') {
      const expectedTargetType =
        input.requestType === 'create-privileged-assignment'
          ? 'workforce-subject'
          : 'workforce-role';
      if (input.targetType !== expectedTargetType) {
        throw new WorkforceAuthorizationValidationError(
          'Change request target does not match its request type.',
        );
      }
      return this.repository.createChangeRequest({
        ...input,
        requesterRef: principalReference(principal),
        expiresAt: new Date(Date.now() + PRIVILEGED_REQUEST_TTL_MS),
      });
    }
    throw new WorkforceAuthorizationValidationError(
      'Change requests are reserved for privileged authorization changes.',
    );
  }

  decideChangeRequest(
    principal: AccessPrincipal,
    input: {
      requestId: string;
      decision: 'approved' | 'rejected';
      evidenceRef: string;
      reason: string | null;
      correlationId: string;
    },
  ) {
    const approverRef = principalReference(principal);
    return this.repository.decideChangeRequest(
      input.requestId,
      input.decision,
      approverRef,
      input.evidenceRef,
      input.reason,
      input.correlationId,
      new Date(),
    );
  }
}
