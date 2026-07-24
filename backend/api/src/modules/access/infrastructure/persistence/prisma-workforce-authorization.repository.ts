import { Injectable } from '@nestjs/common';
import {
  Prisma,
  WorkforceAssignmentStatus,
  WorkforceCapabilityRiskTier,
  WorkforceRoleStatus,
  WorkforceScopeType,
} from '../../../../generated/prisma/client';
import { PrismaService } from '../../../../platform/database/prisma.service';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import {
  WorkforceAuthorizationConflictError,
  WorkforceAuthorizationForbiddenError,
  WorkforceAuthorizationNotFoundError,
  WorkforceAuthorizationValidationError,
} from '../../application/errors/workforce-authorization.errors';
import {
  WorkforceAuthorizationRepository,
  type CreateAssignmentCommand,
  type CreateChangeRequestCommand,
  type CreateWorkforceRoleCommand,
  type ReplaceRoleCapabilitiesCommand,
  type UpdateWorkforceRoleCommand,
} from '../../application/ports/workforce-authorization.repository';
import type {
  AuthorizationChangeRequestView,
  AuthorizationScope,
  CapabilityDefinition,
  CapabilityRiskTier,
  WorkforceAssignmentView,
  WorkforceAuditEventView,
  WorkforceDirectorySubjectView,
  WorkforceEntitlements,
  WorkforceOrganizationUnitView,
  WorkforceRoleView,
  WorkforceScopeType as DomainScopeType,
} from '../../domain/workforce-authorization';
import { isScopeValid } from '../../domain/workforce-authorization';

type Transaction = Prisma.TransactionClient;
const ADMIN_CAPABILITIES = [
  'authorization.assignment.create',
  'authorization.approval.approve',
] as const;

const roleSelection = {
  createdAt: true,
  description: true,
  displayName: true,
  id: true,
  key: true,
  roleCapabilities: { select: { capabilityKey: true } },
  status: true,
  system: true,
  updatedAt: true,
  version: true,
} as const;

function riskTier(value: WorkforceCapabilityRiskTier): CapabilityRiskTier {
  return value.toLowerCase() as CapabilityRiskTier;
}

function scopeType(value: WorkforceScopeType): DomainScopeType {
  return value.toLowerCase() as DomainScopeType;
}

function prismaScopeType(value: DomainScopeType): WorkforceScopeType {
  return value.toUpperCase() as WorkforceScopeType;
}

function roleView(row: {
  id: string;
  key: string;
  displayName: string;
  description: string | null;
  status: WorkforceRoleStatus;
  system: boolean;
  version: number;
  roleCapabilities: readonly { capabilityKey: string }[];
  createdAt: Date;
  updatedAt: Date;
}): WorkforceRoleView {
  return {
    capabilityKeys: row.roleCapabilities
      .map(({ capabilityKey }) => capabilityKey)
      .sort(),
    createdAt: row.createdAt,
    description: row.description,
    displayName: row.displayName,
    id: row.id,
    key: row.key,
    status: row.status.toLowerCase() as 'active' | 'disabled',
    system: row.system,
    updatedAt: row.updatedAt,
    version: row.version,
  };
}

function assignmentView(row: {
  id: string;
  identitySubjectId: string;
  roleId: string;
  role: { key: string };
  status: WorkforceAssignmentStatus;
  effectiveAt: Date;
  expiresAt: Date | null;
  reason: string;
  version: number;
  scopes: readonly {
    scopeType: WorkforceScopeType;
    scopeRef: string;
  }[];
}): WorkforceAssignmentView {
  return {
    effectiveAt: row.effectiveAt,
    expiresAt: row.expiresAt,
    id: row.id,
    identitySubjectId: row.identitySubjectId,
    reason: row.reason,
    roleId: row.roleId,
    roleKey: row.role.key,
    scopes: row.scopes.map((scope) => ({
      type: scopeType(scope.scopeType),
      ref: scope.scopeRef,
    })),
    status: row.status.toLowerCase() as 'active' | 'revoked',
    version: row.version,
  };
}

function changeRequestView(row: {
  id: string;
  requestType: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  riskTier: WorkforceCapabilityRiskTier;
  requesterRef: string;
  targetType: string;
  targetRef: string;
  reason: string;
  payload: Prisma.JsonValue;
  expiresAt: Date;
  decidedAt: Date | null;
}): AuthorizationChangeRequestView {
  return {
    decidedAt: row.decidedAt,
    expiresAt: row.expiresAt,
    id: row.id,
    payload: row.payload,
    reason: row.reason,
    requesterRef: row.requesterRef,
    requestType: row.requestType,
    riskTier: riskTier(row.riskTier),
    status: row.status.toLowerCase() as 'pending' | 'approved' | 'rejected',
    targetRef: row.targetRef,
    targetType: row.targetType,
  };
}

async function writeEvidence(
  transaction: Transaction,
  input: {
    action: string;
    actorRef: string;
    aggregateId: string;
    aggregateType: string;
    correlationId: string;
    eventType: string;
    metadata: Prisma.InputJsonValue;
  },
): Promise<void> {
  await transaction.auditEvent.create({
    data: {
      action: input.action,
      actorRef: input.actorRef,
      actorType: 'workforce',
      correlationId: input.correlationId,
      metadata: input.metadata,
      outcome: 'succeeded',
      resourceId: input.aggregateId,
      resourceType: input.aggregateType,
    },
  });
  await transaction.outboxEvent.create({
    data: {
      aggregateId: input.aggregateId,
      aggregateType: input.aggregateType,
      correlationId: input.correlationId,
      eventType: input.eventType,
      eventVersion: 1,
      payload: input.metadata,
    },
  });
}

async function bumpEntitlementRevision(
  transaction: Transaction,
  identitySubjectId: string,
): Promise<void> {
  await transaction.workforceEntitlementRevision.upsert({
    create: { identitySubjectId, revision: 1 },
    update: { revision: { increment: 1 } },
    where: { identitySubjectId },
  });
}

async function bumpRoleSubjects(
  transaction: Transaction,
  roleId: string,
): Promise<void> {
  const assignments = await transaction.workforceRoleAssignment.findMany({
    distinct: ['identitySubjectId'],
    select: { identitySubjectId: true },
    where: { roleId, status: WorkforceAssignmentStatus.ACTIVE },
  });
  await Promise.all(
    assignments.map(({ identitySubjectId }) =>
      bumpEntitlementRevision(transaction, identitySubjectId),
    ),
  );
}

function hasAdministratorCapabilities(keys: Iterable<string>): boolean {
  const observed = new Set(keys);
  return ADMIN_CAPABILITIES.every((key) => observed.has(key));
}

async function assertAnotherGlobalAdministrator(
  transaction: Transaction,
  excludedRoleId: string,
  now: Date,
): Promise<void> {
  const assignments = await transaction.workforceRoleAssignment.findMany({
    select: {
      role: {
        select: {
          roleCapabilities: { select: { capabilityKey: true } },
        },
      },
      scopes: { select: { scopeType: true } },
    },
    where: {
      effectiveAt: { lte: now },
      identitySubject: { realm: 'workforce', status: 'active' },
      OR: [{ expiresAt: null }, { expiresAt: { gt: now } }],
      role: { status: WorkforceRoleStatus.ACTIVE },
      roleId: { not: excludedRoleId },
      status: WorkforceAssignmentStatus.ACTIVE,
    },
  });
  const exists = assignments.some(
    (assignment) =>
      assignment.scopes.some(
        ({ scopeType: observedScopeType }) =>
          observedScopeType === WorkforceScopeType.GLOBAL,
      ) &&
      hasAdministratorCapabilities(
        assignment.role.roleCapabilities.map(
          ({ capabilityKey }) => capabilityKey,
        ),
      ),
  );
  if (!exists) {
    throw new WorkforceAuthorizationForbiddenError(
      'The final active global authorization administrator must be preserved.',
    );
  }
}

async function scopedRows(
  transaction: Transaction,
  scopes: readonly AuthorizationScope[],
): Promise<
  Array<{
    scopeType: WorkforceScopeType;
    scopeRef: string;
    organizationUnitId: string | null;
  }>
> {
  const rows = [];
  for (const scope of scopes) {
    if (scope.type === 'global') {
      rows.push({
        scopeType: WorkforceScopeType.GLOBAL,
        scopeRef: 'global',
        organizationUnitId: null,
      });
      continue;
    }
    const unit =
      await transaction.workforceOrganizationUnitProjection.findUnique({
        select: { id: true, status: true, type: true },
        where: { externalRef: scope.ref },
      });
    if (
      unit === null ||
      unit.status !== 'active' ||
      scopeType(unit.type) !== scope.type
    ) {
      throw new WorkforceAuthorizationValidationError(
        `Unknown or inactive ${scope.type} scope.`,
      );
    }
    rows.push({
      scopeType: prismaScopeType(scope.type),
      scopeRef: scope.ref,
      organizationUnitId: unit.id,
    });
  }
  return rows;
}

@Injectable()
export class PrismaWorkforceAuthorizationRepository extends WorkforceAuthorizationRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async resolveEntitlements(
    principal: AccessPrincipal,
    now: Date,
  ): Promise<WorkforceEntitlements | null> {
    const subject = await this.prisma.identitySubject.findUnique({
      select: {
        id: true,
        status: true,
        workforceAssignments: {
          select: {
            role: {
              select: {
                roleCapabilities: {
                  select: {
                    capability: {
                      select: {
                        deprecated: true,
                        key: true,
                        riskTier: true,
                      },
                    },
                  },
                },
                status: true,
              },
            },
            scopes: { select: { scopeRef: true, scopeType: true } },
          },
          where: {
            effectiveAt: { lte: now },
            OR: [{ expiresAt: null }, { expiresAt: { gt: now } }],
            status: WorkforceAssignmentStatus.ACTIVE,
          },
        },
        workforceEntitlementRevision: { select: { revision: true } },
      },
      where: {
        issuer_subject: {
          issuer: principal.issuer,
          subject: principal.subject,
        },
      },
    });
    if (
      subject === null ||
      subject.status !== 'active' ||
      principal.realm !== 'workforce'
    ) {
      return null;
    }

    const grants = new Map<
      string,
      {
        key: string;
        riskTier: CapabilityRiskTier;
        scopes: AuthorizationScope[];
      }
    >();
    for (const assignment of subject.workforceAssignments) {
      if (assignment.role.status !== WorkforceRoleStatus.ACTIVE) continue;
      const scopes = assignment.scopes.map((scope) => ({
        type: scopeType(scope.scopeType),
        ref: scope.scopeRef,
      }));
      for (const { capability } of assignment.role.roleCapabilities) {
        if (capability.deprecated) continue;
        const existing = grants.get(capability.key);
        if (existing === undefined) {
          grants.set(capability.key, {
            key: capability.key,
            riskTier: riskTier(capability.riskTier),
            scopes: [...scopes],
          });
        } else {
          const known = new Set(
            existing.scopes.map((scope) => `${scope.type}:${scope.ref}`),
          );
          existing.scopes.push(
            ...scopes.filter(
              (scope) => !known.has(`${scope.type}:${scope.ref}`),
            ),
          );
        }
      }
    }
    return {
      identitySubjectId: subject.id,
      revision: String(subject.workforceEntitlementRevision?.revision ?? 0),
      capabilities: [...grants.values()].sort((a, b) =>
        a.key.localeCompare(b.key),
      ),
    };
  }

  async listCapabilities(): Promise<readonly CapabilityDefinition[]> {
    const rows = await this.prisma.workforceCapabilityDefinition.findMany({
      orderBy: { key: 'asc' },
    });
    return rows.map((row) => ({
      ...row,
      riskTier: riskTier(row.riskTier),
    }));
  }

  async listRoles(): Promise<readonly WorkforceRoleView[]> {
    const rows = await this.prisma.workforceRole.findMany({
      orderBy: { displayName: 'asc' },
      select: roleSelection,
    });
    return rows.map(roleView);
  }

  async getRole(roleId: string): Promise<WorkforceRoleView | null> {
    const row = await this.prisma.workforceRole.findUnique({
      select: roleSelection,
      where: { id: roleId },
    });
    return row === null ? null : roleView(row);
  }

  async isRoleAssignedToPrincipal(
    roleId: string,
    principal: AccessPrincipal,
    now: Date,
  ): Promise<boolean> {
    const assignment = await this.prisma.workforceRoleAssignment.findFirst({
      select: { id: true },
      where: {
        effectiveAt: { lte: now },
        identitySubject: {
          issuer: principal.issuer,
          realm: 'workforce',
          status: 'active',
          subject: principal.subject,
        },
        OR: [{ expiresAt: null }, { expiresAt: { gt: now } }],
        role: { status: WorkforceRoleStatus.ACTIVE },
        roleId,
        status: WorkforceAssignmentStatus.ACTIVE,
      },
    });
    return assignment !== null;
  }

  createRole(command: CreateWorkforceRoleCommand): Promise<WorkforceRoleView> {
    return this.prisma.$transaction(async (transaction) => {
      try {
        const role = await transaction.workforceRole.create({
          data: {
            createdByRef: command.actorRef,
            description: command.description,
            displayName: command.displayName,
            key: command.key,
            updatedByRef: command.actorRef,
          },
          select: roleSelection,
        });
        await writeEvidence(transaction, {
          action: 'authorization.role.create',
          actorRef: command.actorRef,
          aggregateId: role.id,
          aggregateType: 'workforce_role',
          correlationId: command.correlationId,
          eventType: 'workforce.role.created',
          metadata: {
            roleId: role.id,
            roleKey: role.key,
            version: role.version,
          },
        });
        return roleView(role);
      } catch (error) {
        if (
          error instanceof Prisma.PrismaClientKnownRequestError &&
          error.code === 'P2002'
        ) {
          throw new WorkforceAuthorizationConflictError(
            'The role key already exists.',
          );
        }
        throw error;
      }
    });
  }

  updateRole(command: UpdateWorkforceRoleCommand): Promise<WorkforceRoleView> {
    return this.prisma.$transaction(async (transaction) => {
      const result = await transaction.workforceRole.updateMany({
        data: {
          ...(command.displayName === undefined
            ? {}
            : { displayName: command.displayName }),
          ...(command.description === undefined
            ? {}
            : { description: command.description }),
          updatedByRef: command.actorRef,
          version: { increment: 1 },
        },
        where: {
          id: command.roleId,
          status: WorkforceRoleStatus.ACTIVE,
          version: command.expectedVersion,
        },
      });
      if (result.count !== 1) {
        throw new WorkforceAuthorizationConflictError(
          'The role changed or is not active.',
        );
      }
      const role = await transaction.workforceRole.findUniqueOrThrow({
        select: roleSelection,
        where: { id: command.roleId },
      });
      await writeEvidence(transaction, {
        action: 'authorization.role.update',
        actorRef: command.actorRef,
        aggregateId: role.id,
        aggregateType: 'workforce_role',
        correlationId: command.correlationId,
        eventType: 'workforce.role.updated',
        metadata: { roleId: role.id, version: role.version },
      });
      return roleView(role);
    });
  }

  replaceRoleCapabilities(
    command: ReplaceRoleCapabilitiesCommand,
  ): Promise<WorkforceRoleView> {
    return this.prisma.$transaction(async (transaction) => {
      const capabilities =
        await transaction.workforceCapabilityDefinition.findMany({
          select: { key: true },
          where: {
            deprecated: false,
            key: { in: [...new Set(command.capabilityKeys)] },
          },
        });
      if (capabilities.length !== new Set(command.capabilityKeys).size) {
        throw new WorkforceAuthorizationValidationError(
          'Role contains an unknown or deprecated capability.',
        );
      }
      const updated = await transaction.workforceRole.updateMany({
        data: {
          updatedByRef: command.actorRef,
          version: { increment: 1 },
        },
        where: {
          id: command.roleId,
          status: WorkforceRoleStatus.ACTIVE,
          version: command.expectedVersion,
        },
      });
      if (updated.count !== 1) {
        throw new WorkforceAuthorizationConflictError(
          'The role changed or is not active.',
        );
      }
      await transaction.workforceRoleCapability.deleteMany({
        where: { roleId: command.roleId },
      });
      if (capabilities.length > 0) {
        await transaction.workforceRoleCapability.createMany({
          data: capabilities.map(({ key }) => ({
            capabilityKey: key,
            grantedByRef: command.actorRef,
            roleId: command.roleId,
          })),
        });
      }
      await bumpRoleSubjects(transaction, command.roleId);
      const role = await transaction.workforceRole.findUniqueOrThrow({
        select: roleSelection,
        where: { id: command.roleId },
      });
      await writeEvidence(transaction, {
        action: 'authorization.role.capabilities.replace',
        actorRef: command.actorRef,
        aggregateId: role.id,
        aggregateType: 'workforce_role',
        correlationId: command.correlationId,
        eventType: 'workforce.role.capabilities-replaced',
        metadata: {
          capabilityKeys: capabilities.map(({ key }) => key),
          roleId: role.id,
          version: role.version,
        },
      });
      return roleView(role);
    });
  }

  disableRole(
    roleId: string,
    expectedVersion: number,
    actorRef: string,
    correlationId: string,
  ): Promise<WorkforceRoleView> {
    return this.prisma.$transaction(async (transaction) => {
      const role = await transaction.workforceRole.findUnique({
        select: { key: true, system: true },
        where: { id: roleId },
      });
      if (role === null) {
        throw new WorkforceAuthorizationNotFoundError('Role not found.');
      }
      if (role.system) {
        throw new WorkforceAuthorizationForbiddenError(
          'System roles cannot be disabled.',
        );
      }
      const updated = await transaction.workforceRole.updateMany({
        data: {
          status: WorkforceRoleStatus.DISABLED,
          updatedByRef: actorRef,
          version: { increment: 1 },
        },
        where: {
          id: roleId,
          status: WorkforceRoleStatus.ACTIVE,
          version: expectedVersion,
        },
      });
      if (updated.count !== 1) {
        throw new WorkforceAuthorizationConflictError(
          'The role changed or is not active.',
        );
      }
      await bumpRoleSubjects(transaction, roleId);
      const result = await transaction.workforceRole.findUniqueOrThrow({
        select: roleSelection,
        where: { id: roleId },
      });
      await writeEvidence(transaction, {
        action: 'authorization.role.disable',
        actorRef,
        aggregateId: roleId,
        aggregateType: 'workforce_role',
        correlationId,
        eventType: 'workforce.role.disabled',
        metadata: { roleId, version: result.version },
      });
      return roleView(result);
    });
  }

  async listAssignments(): Promise<readonly WorkforceAssignmentView[]> {
    const rows = await this.prisma.workforceRoleAssignment.findMany({
      orderBy: { createdAt: 'desc' },
      select: {
        effectiveAt: true,
        expiresAt: true,
        id: true,
        identitySubjectId: true,
        reason: true,
        role: { select: { key: true } },
        roleId: true,
        scopes: { select: { scopeRef: true, scopeType: true } },
        status: true,
        version: true,
      },
    });
    return rows.map(assignmentView);
  }

  createAssignment(
    command: CreateAssignmentCommand,
  ): Promise<WorkforceAssignmentView> {
    return this.prisma.$transaction(async (transaction) => {
      const target = await transaction.identitySubject.findUnique({
        select: { issuer: true, realm: true, status: true, subject: true },
        where: { id: command.identitySubjectId },
      });
      if (
        target === null ||
        target.realm !== 'workforce' ||
        target.status !== 'active'
      ) {
        throw new WorkforceAuthorizationNotFoundError(
          'Active workforce identity not found.',
        );
      }
      if (`${target.issuer}|${target.subject}` === command.actorRef) {
        throw new WorkforceAuthorizationForbiddenError(
          'Self-assignment is not permitted.',
        );
      }
      const role = await transaction.workforceRole.findUnique({
        select: { status: true },
        where: { id: command.roleId },
      });
      if (role?.status !== WorkforceRoleStatus.ACTIVE) {
        throw new WorkforceAuthorizationNotFoundError('Active role not found.');
      }
      const scopes = await scopedRows(transaction, command.scopes);
      const row = await transaction.workforceRoleAssignment.create({
        data: {
          createdByRef: command.actorRef,
          effectiveAt: command.effectiveAt,
          expiresAt: command.expiresAt,
          identitySubjectId: command.identitySubjectId,
          reason: command.reason,
          roleId: command.roleId,
          scopes: { createMany: { data: scopes } },
        },
        select: {
          effectiveAt: true,
          expiresAt: true,
          id: true,
          identitySubjectId: true,
          reason: true,
          role: { select: { key: true } },
          roleId: true,
          scopes: { select: { scopeRef: true, scopeType: true } },
          status: true,
          version: true,
        },
      });
      await bumpEntitlementRevision(transaction, command.identitySubjectId);
      await writeEvidence(transaction, {
        action: 'authorization.assignment.create',
        actorRef: command.actorRef,
        aggregateId: row.id,
        aggregateType: 'workforce_role_assignment',
        correlationId: command.correlationId,
        eventType: 'workforce.assignment.created',
        metadata: {
          assignmentId: row.id,
          identitySubjectId: command.identitySubjectId,
          roleId: command.roleId,
        },
      });
      return assignmentView(row);
    });
  }

  revokeAssignment(
    assignmentId: string,
    expectedVersion: number,
    actorRef: string,
    correlationId: string,
  ): Promise<WorkforceAssignmentView> {
    return this.prisma.$transaction(async (transaction) => {
      const current = await transaction.workforceRoleAssignment.findUnique({
        select: {
          identitySubject: { select: { status: true } },
          identitySubjectId: true,
          role: {
            select: {
              roleCapabilities: { select: { capabilityKey: true } },
              status: true,
            },
          },
          scopes: { select: { scopeType: true } },
        },
        where: { id: assignmentId },
      });
      if (current === null) {
        throw new WorkforceAuthorizationNotFoundError('Assignment not found.');
      }
      const now = new Date();
      const currentCapabilities = new Set(
        current.role.roleCapabilities.map(({ capabilityKey }) => capabilityKey),
      );
      const isGlobalAdministrator =
        current.identitySubject.status === 'active' &&
        current.role.status === WorkforceRoleStatus.ACTIVE &&
        current.scopes.some(
          ({ scopeType: currentScopeType }) =>
            currentScopeType === WorkforceScopeType.GLOBAL,
        ) &&
        hasAdministratorCapabilities(currentCapabilities);
      if (isGlobalAdministrator) {
        const otherAssignments =
          await transaction.workforceRoleAssignment.findMany({
            select: {
              role: {
                select: {
                  roleCapabilities: { select: { capabilityKey: true } },
                },
              },
              scopes: { select: { scopeType: true } },
            },
            where: {
              effectiveAt: { lte: now },
              identitySubject: { realm: 'workforce', status: 'active' },
              id: { not: assignmentId },
              OR: [{ expiresAt: null }, { expiresAt: { gt: now } }],
              role: { status: WorkforceRoleStatus.ACTIVE },
              status: WorkforceAssignmentStatus.ACTIVE,
            },
          });
        const anotherAdministratorExists = otherAssignments.some(
          (assignment) => {
            const keys = new Set(
              assignment.role.roleCapabilities.map(
                ({ capabilityKey }) => capabilityKey,
              ),
            );
            return (
              assignment.scopes.some(
                ({ scopeType: assignmentScopeType }) =>
                  assignmentScopeType === WorkforceScopeType.GLOBAL,
              ) && hasAdministratorCapabilities(keys)
            );
          },
        );
        if (!anotherAdministratorExists) {
          throw new WorkforceAuthorizationForbiddenError(
            'The final active global authorization administrator cannot be revoked.',
          );
        }
      }
      const result = await transaction.workforceRoleAssignment.updateMany({
        data: {
          revokedAt: now,
          revokedByRef: actorRef,
          status: WorkforceAssignmentStatus.REVOKED,
          version: { increment: 1 },
        },
        where: {
          id: assignmentId,
          status: WorkforceAssignmentStatus.ACTIVE,
          version: expectedVersion,
        },
      });
      if (result.count !== 1) {
        throw new WorkforceAuthorizationConflictError(
          'The assignment changed or is not active.',
        );
      }
      await bumpEntitlementRevision(transaction, current.identitySubjectId);
      const row = await transaction.workforceRoleAssignment.findUniqueOrThrow({
        select: {
          effectiveAt: true,
          expiresAt: true,
          id: true,
          identitySubjectId: true,
          reason: true,
          role: { select: { key: true } },
          roleId: true,
          scopes: { select: { scopeRef: true, scopeType: true } },
          status: true,
          version: true,
        },
        where: { id: assignmentId },
      });
      await writeEvidence(transaction, {
        action: 'authorization.assignment.revoke',
        actorRef,
        aggregateId: assignmentId,
        aggregateType: 'workforce_role_assignment',
        correlationId,
        eventType: 'workforce.assignment.revoked',
        metadata: {
          assignmentId,
          identitySubjectId: current.identitySubjectId,
        },
      });
      return assignmentView(row);
    });
  }

  async listDirectorySubjects(): Promise<
    readonly WorkforceDirectorySubjectView[]
  > {
    const rows = await this.prisma.identitySubject.findMany({
      orderBy: { createdAt: 'desc' },
      select: { id: true, status: true, subject: true },
      take: 100,
      where: { realm: 'workforce' },
    });
    return rows.map((row) => ({
      externalSubject: row.subject,
      id: row.id,
      status: row.status,
    }));
  }

  async listOrganizationUnits(): Promise<
    readonly WorkforceOrganizationUnitView[]
  > {
    const rows = await this.prisma.workforceOrganizationUnitProjection.findMany(
      {
        orderBy: [{ type: 'asc' }, { displayName: 'asc' }],
        take: 500,
      },
    );
    return rows.map((row) => ({
      displayName: row.displayName,
      externalRef: row.externalRef,
      id: row.id,
      observedAt: row.observedAt,
      revision: row.revision,
      source: row.source,
      status: row.status,
      type: scopeType(row.type),
    }));
  }

  async listAuditEvents(): Promise<readonly WorkforceAuditEventView[]> {
    return this.prisma.auditEvent.findMany({
      orderBy: { occurredAt: 'desc' },
      select: {
        action: true,
        actorRef: true,
        correlationId: true,
        id: true,
        occurredAt: true,
        outcome: true,
        resourceId: true,
        resourceType: true,
      },
      take: 100,
      where: { actorType: 'workforce' },
    });
  }

  async listChangeRequests(): Promise<
    readonly AuthorizationChangeRequestView[]
  > {
    const rows = await this.prisma.authorizationChangeRequest.findMany({
      orderBy: { createdAt: 'desc' },
    });
    return rows.map(changeRequestView);
  }

  createChangeRequest(
    command: CreateChangeRequestCommand,
  ): Promise<AuthorizationChangeRequestView> {
    return this.prisma.$transaction(async (transaction) => {
      const row = await transaction.authorizationChangeRequest.create({
        data: {
          correlationId: command.correlationId,
          expiresAt: command.expiresAt,
          payload: command.payload as Prisma.InputJsonValue,
          reason: command.reason,
          requesterRef: command.requesterRef,
          requestType: command.requestType,
          riskTier:
            command.riskTier.toUpperCase() as WorkforceCapabilityRiskTier,
          targetRef: command.targetRef,
          targetType: command.targetType,
        },
      });
      await writeEvidence(transaction, {
        action: 'authorization.change-request.create',
        actorRef: command.requesterRef,
        aggregateId: row.id,
        aggregateType: 'authorization_change_request',
        correlationId: command.correlationId,
        eventType: 'workforce.authorization-change.requested',
        metadata: {
          changeRequestId: row.id,
          requestType: row.requestType,
          targetRef: row.targetRef,
          targetType: row.targetType,
        },
      });
      return changeRequestView(row);
    });
  }

  decideChangeRequest(
    requestId: string,
    decision: 'approved' | 'rejected',
    approverRef: string,
    evidenceRef: string,
    reason: string | null,
    correlationId: string,
    now: Date,
  ): Promise<AuthorizationChangeRequestView> {
    return this.prisma.$transaction(async (transaction) => {
      const request = await transaction.authorizationChangeRequest.findUnique({
        where: { id: requestId },
      });
      if (request === null) {
        throw new WorkforceAuthorizationNotFoundError(
          'Change request not found.',
        );
      }
      if (
        request.status !== 'PENDING' ||
        request.expiresAt.getTime() <= now.getTime()
      ) {
        throw new WorkforceAuthorizationConflictError(
          'The change request is no longer pending.',
        );
      }
      if (request.requesterRef === approverRef) {
        throw new WorkforceAuthorizationForbiddenError(
          'The requester cannot approve or reject their own request.',
        );
      }
      const updated = await transaction.authorizationChangeRequest.updateMany({
        data: {
          decidedAt: now,
          status: decision === 'approved' ? 'APPROVED' : 'REJECTED',
        },
        where: { id: requestId, status: 'PENDING' },
      });
      if (updated.count !== 1) {
        throw new WorkforceAuthorizationConflictError(
          'The change request was decided concurrently.',
        );
      }
      await transaction.authorizationChangeApproval.create({
        data: {
          approverRef,
          changeRequestId: requestId,
          decidedAt: now,
          decision,
          evidenceRef,
          reason,
        },
      });
      if (decision === 'approved') {
        await this.applyApprovedRequest(transaction, request, approverRef, now);
      }
      await writeEvidence(transaction, {
        action: `authorization.change-request.${decision}`,
        actorRef: approverRef,
        aggregateId: requestId,
        aggregateType: 'authorization_change_request',
        correlationId,
        eventType: `workforce.authorization-change.${decision}`,
        metadata: { changeRequestId: requestId, targetRef: request.targetRef },
      });
      const result =
        await transaction.authorizationChangeRequest.findUniqueOrThrow({
          where: { id: requestId },
        });
      return changeRequestView(result);
    });
  }

  private async applyApprovedRequest(
    transaction: Transaction,
    request: {
      requestType: string;
      targetRef: string;
      payload: Prisma.JsonValue;
      requesterRef: string;
      correlationId: string;
    },
    approverRef: string,
    now: Date,
  ): Promise<void> {
    if (
      typeof request.payload !== 'object' ||
      request.payload === null ||
      Array.isArray(request.payload)
    ) {
      throw new WorkforceAuthorizationValidationError(
        'Change request payload is invalid.',
      );
    }
    const payload = request.payload as Record<string, Prisma.JsonValue>;
    if (request.requestType === 'replace-role-capabilities') {
      const expectedVersion = Number(payload.expectedVersion);
      const capabilityKeys = payload.capabilityKeys;
      if (
        !Number.isInteger(expectedVersion) ||
        !Array.isArray(capabilityKeys) ||
        !capabilityKeys.every((key) => typeof key === 'string')
      ) {
        throw new WorkforceAuthorizationValidationError(
          'Role capability request payload is invalid.',
        );
      }
      const result = await transaction.workforceRole.updateMany({
        data: { updatedByRef: approverRef, version: { increment: 1 } },
        where: {
          id: request.targetRef,
          status: WorkforceRoleStatus.ACTIVE,
          version: expectedVersion,
        },
      });
      if (result.count !== 1) {
        throw new WorkforceAuthorizationConflictError(
          'The target role changed before approval.',
        );
      }
      const definitions =
        await transaction.workforceCapabilityDefinition.findMany({
          select: { key: true },
          where: {
            deprecated: false,
            key: { in: capabilityKeys },
          },
        });
      if (definitions.length !== new Set(capabilityKeys).size) {
        throw new WorkforceAuthorizationValidationError(
          'Approved role contains an unknown capability.',
        );
      }
      const currentCapabilities =
        await transaction.workforceRoleCapability.findMany({
          select: { capabilityKey: true },
          where: { roleId: request.targetRef },
        });
      if (
        hasAdministratorCapabilities(
          currentCapabilities.map(({ capabilityKey }) => capabilityKey),
        ) &&
        !hasAdministratorCapabilities(capabilityKeys)
      ) {
        await assertAnotherGlobalAdministrator(
          transaction,
          request.targetRef,
          now,
        );
      }
      await transaction.workforceRoleCapability.deleteMany({
        where: { roleId: request.targetRef },
      });
      await transaction.workforceRoleCapability.createMany({
        data: definitions.map(({ key }) => ({
          capabilityKey: key,
          grantedByRef: approverRef,
          roleId: request.targetRef,
        })),
      });
      await bumpRoleSubjects(transaction, request.targetRef);
      return;
    }
    if (request.requestType === 'disable-role') {
      const expectedVersion = Number(payload.expectedVersion);
      const role = await transaction.workforceRole.findUnique({
        select: { system: true },
        where: { id: request.targetRef },
      });
      if (role?.system) {
        throw new WorkforceAuthorizationForbiddenError(
          'System roles cannot be disabled.',
        );
      }
      const currentCapabilities =
        await transaction.workforceRoleCapability.findMany({
          select: { capabilityKey: true },
          where: { roleId: request.targetRef },
        });
      if (
        hasAdministratorCapabilities(
          currentCapabilities.map(({ capabilityKey }) => capabilityKey),
        )
      ) {
        await assertAnotherGlobalAdministrator(
          transaction,
          request.targetRef,
          now,
        );
      }
      const result = await transaction.workforceRole.updateMany({
        data: {
          status: WorkforceRoleStatus.DISABLED,
          updatedByRef: approverRef,
          version: { increment: 1 },
        },
        where: {
          id: request.targetRef,
          status: WorkforceRoleStatus.ACTIVE,
          version: expectedVersion,
        },
      });
      if (result.count !== 1) {
        throw new WorkforceAuthorizationConflictError(
          'The target role changed before approval.',
        );
      }
      await bumpRoleSubjects(transaction, request.targetRef);
      return;
    }
    if (request.requestType === 'create-privileged-assignment') {
      const roleId = payload.roleId;
      const effectiveAtValue = payload.effectiveAt;
      const expiresAtValue = payload.expiresAt;
      const reason = payload.reason;
      const requestedScopes = payload.scopes;
      if (
        typeof roleId !== 'string' ||
        typeof effectiveAtValue !== 'string' ||
        typeof expiresAtValue !== 'string' ||
        typeof reason !== 'string' ||
        reason.length < 8 ||
        !Array.isArray(requestedScopes)
      ) {
        throw new WorkforceAuthorizationValidationError(
          'Privileged assignment request payload is invalid.',
        );
      }
      const effectiveAt = new Date(effectiveAtValue);
      const expiresAt = new Date(expiresAtValue);
      if (
        Number.isNaN(effectiveAt.getTime()) ||
        Number.isNaN(expiresAt.getTime()) ||
        expiresAt.getTime() <= effectiveAt.getTime() ||
        expiresAt.getTime() - effectiveAt.getTime() > 90 * 24 * 60 * 60 * 1000
      ) {
        throw new WorkforceAuthorizationValidationError(
          'Privileged assignment expiry must be after activation and within 90 days.',
        );
      }
      const scopes: AuthorizationScope[] = requestedScopes.map((scope) => {
        if (
          typeof scope !== 'object' ||
          scope === null ||
          Array.isArray(scope) ||
          typeof scope.type !== 'string' ||
          typeof scope.ref !== 'string'
        ) {
          throw new WorkforceAuthorizationValidationError(
            'Privileged assignment scope is invalid.',
          );
        }
        return {
          type: scope.type as DomainScopeType,
          ref: scope.ref,
        };
      });
      if (scopes.length === 0 || scopes.some((scope) => !isScopeValid(scope))) {
        throw new WorkforceAuthorizationValidationError(
          'Privileged assignment requires valid organizational scopes.',
        );
      }
      const target = await transaction.identitySubject.findUnique({
        select: { issuer: true, realm: true, status: true, subject: true },
        where: { id: request.targetRef },
      });
      if (
        target === null ||
        target.realm !== 'workforce' ||
        target.status !== 'active'
      ) {
        throw new WorkforceAuthorizationNotFoundError(
          'Active workforce identity not found.',
        );
      }
      if (`${target.issuer}|${target.subject}` === request.requesterRef) {
        throw new WorkforceAuthorizationForbiddenError(
          'Self-assignment is not permitted.',
        );
      }
      const role = await transaction.workforceRole.findUnique({
        select: {
          roleCapabilities: {
            select: {
              capability: { select: { riskTier: true } },
            },
          },
          status: true,
        },
        where: { id: roleId },
      });
      if (
        role?.status !== WorkforceRoleStatus.ACTIVE ||
        !role.roleCapabilities.some(
          ({ capability }) =>
            capability.riskTier === WorkforceCapabilityRiskTier.PRIVILEGED,
        )
      ) {
        throw new WorkforceAuthorizationValidationError(
          'The selected role is not an active privileged role.',
        );
      }
      const persistedScopes = await scopedRows(transaction, scopes);
      const assignment = await transaction.workforceRoleAssignment.create({
        data: {
          approvedByRef: approverRef,
          createdByRef: request.requesterRef,
          effectiveAt,
          expiresAt,
          identitySubjectId: request.targetRef,
          reason,
          roleId,
          scopes: { createMany: { data: persistedScopes } },
        },
      });
      await bumpEntitlementRevision(transaction, request.targetRef);
      await writeEvidence(transaction, {
        action: 'authorization.assignment.create-privileged',
        actorRef: approverRef,
        aggregateId: assignment.id,
        aggregateType: 'workforce_role_assignment',
        correlationId: request.correlationId,
        eventType: 'workforce.assignment.privileged-created',
        metadata: {
          assignmentId: assignment.id,
          identitySubjectId: request.targetRef,
          roleId,
        },
      });
      return;
    }
    throw new WorkforceAuthorizationValidationError(
      'Unsupported authorization change request type.',
    );
  }
}
