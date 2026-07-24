import 'dotenv/config';
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { PrismaPg } from '@prisma/adapter-pg';
import {
  Prisma,
  PrismaClient,
  WorkforceAssignmentStatus,
  WorkforceCapabilityRiskTier,
  WorkforceRoleStatus,
  WorkforceScopeType,
} from '../src/generated/prisma/client';

const BOOTSTRAP_ROLE_KEY = 'authorization-bootstrap-administrator';
const BOOTSTRAP_ACK = 'CREATE_TWO_INITIAL_WORKFORCE_ADMINISTRATORS';
const MAX_BOOTSTRAP_TTL_MS = 24 * 60 * 60 * 1000;
const REQUIRED_ADMIN_CAPABILITIES = [
  'authorization.assignment.create',
  'authorization.approval.approve',
] as const;

interface CapabilityCatalog {
  readonly version: number;
  readonly capabilities: ReadonlyArray<{
    readonly key: string;
    readonly resource: string;
    readonly action: string;
    readonly riskTier: 'standard' | 'sensitive' | 'privileged';
    readonly displayName: string;
  }>;
}

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required.`);
  return value;
}

function administratorSubjects(): readonly [string, string] {
  const values = requiredEnvironment('VFBIZ_BOOTSTRAP_ADMIN_SUBJECTS')
    .split(',')
    .map((value) => value.trim())
    .filter(Boolean);
  if (values.length !== 2 || values[0] === values[1]) {
    throw new Error(
      'VFBIZ_BOOTSTRAP_ADMIN_SUBJECTS must contain exactly two distinct OIDC subjects.',
    );
  }
  return [values[0], values[1]];
}

function assignmentExpiry(now: Date): Date {
  const expiresAt = new Date(
    requiredEnvironment('VFBIZ_BOOTSTRAP_ASSIGNMENT_EXPIRES_AT'),
  );
  if (
    Number.isNaN(expiresAt.getTime()) ||
    expiresAt.getTime() <= now.getTime() ||
    expiresAt.getTime() - now.getTime() > MAX_BOOTSTRAP_TTL_MS
  ) {
    throw new Error(
      'VFBIZ_BOOTSTRAP_ASSIGNMENT_EXPIRES_AT must be in the future and no more than 24 hours from now.',
    );
  }
  return expiresAt;
}

function riskTier(
  value: CapabilityCatalog['capabilities'][number]['riskTier'],
): WorkforceCapabilityRiskTier {
  return value.toUpperCase() as WorkforceCapabilityRiskTier;
}

async function loadCatalog(): Promise<CapabilityCatalog> {
  const path = resolve(
    __dirname,
    '../../../contracts/authorization/workforce-capabilities.json',
  );
  return JSON.parse(await readFile(path, 'utf8')) as CapabilityCatalog;
}

async function activeGlobalAdministratorCount(
  prisma: PrismaClient,
): Promise<number> {
  const assignments = await prisma.workforceRoleAssignment.findMany({
    select: {
      identitySubjectId: true,
      role: {
        select: {
          roleCapabilities: { select: { capabilityKey: true } },
        },
      },
    },
    where: {
      effectiveAt: { lte: new Date() },
      identitySubject: { realm: 'workforce', status: 'active' },
      OR: [{ expiresAt: null }, { expiresAt: { gt: new Date() } }],
      role: { status: WorkforceRoleStatus.ACTIVE },
      scopes: { some: { scopeType: WorkforceScopeType.GLOBAL } },
      status: WorkforceAssignmentStatus.ACTIVE,
    },
  });
  return new Set(
    assignments
      .filter((assignment) => {
        const keys = new Set(
          assignment.role.roleCapabilities.map(
            ({ capabilityKey }) => capabilityKey,
          ),
        );
        return REQUIRED_ADMIN_CAPABILITIES.every((key) => keys.has(key));
      })
      .map(({ identitySubjectId }) => identitySubjectId),
  ).size;
}

async function bootstrap(
  prisma: PrismaClient,
  input: {
    issuer: string;
    subjects: readonly [string, string];
    catalog: CapabilityCatalog;
    expiresAt: Date;
  },
): Promise<void> {
  const observedAdministrators = await activeGlobalAdministratorCount(prisma);
  if (observedAdministrators >= 2) {
    process.stdout.write(
      'At least two active global authorization administrators already exist; no write was performed.\n',
    );
    return;
  }
  if (observedAdministrators === 1) {
    throw new Error(
      'A single active global administrator exists. Use the approved recovery procedure; bootstrap will not mutate a partial authority state.',
    );
  }

  const correlationId = randomUUID();
  const actorRef = 'controlled-bootstrap-command';
  await prisma.$transaction(async (transaction) => {
    for (const capability of input.catalog.capabilities) {
      await transaction.workforceCapabilityDefinition.upsert({
        create: {
          ...capability,
          catalogVersion: input.catalog.version,
          riskTier: riskTier(capability.riskTier),
        },
        update: {
          action: capability.action,
          catalogVersion: input.catalog.version,
          displayName: capability.displayName,
          resource: capability.resource,
          riskTier: riskTier(capability.riskTier),
        },
        where: { key: capability.key },
      });
    }

    const role = await transaction.workforceRole.upsert({
      create: {
        createdByRef: actorRef,
        description:
          'Vai trò hệ thống dùng cho hai quản trị viên authorization ban đầu.',
        displayName: 'Quản trị viên authorization ban đầu',
        key: BOOTSTRAP_ROLE_KEY,
        system: true,
        updatedByRef: actorRef,
      },
      update: {
        status: WorkforceRoleStatus.ACTIVE,
        system: true,
        updatedByRef: actorRef,
      },
      where: { key: BOOTSTRAP_ROLE_KEY },
    });
    await transaction.workforceRoleCapability.createMany({
      data: input.catalog.capabilities.map((capability) => ({
        capabilityKey: capability.key,
        grantedByRef: actorRef,
        roleId: role.id,
      })),
      skipDuplicates: true,
    });

    for (const subject of input.subjects) {
      const identity = await transaction.identitySubject.upsert({
        create: {
          issuer: input.issuer,
          realm: 'workforce',
          subject,
        },
        update: {
          realm: 'workforce',
          status: 'active',
        },
        where: {
          issuer_subject: { issuer: input.issuer, subject },
        },
      });
      const existingAssignment =
        await transaction.workforceRoleAssignment.findFirst({
          select: { id: true },
          where: {
            identitySubjectId: identity.id,
            status: WorkforceAssignmentStatus.ACTIVE,
          },
        });
      if (existingAssignment !== null) {
        throw new Error(
          'A bootstrap subject already has an active assignment. Use the approved authorization change workflow instead.',
        );
      }
      const assignment = await transaction.workforceRoleAssignment.create({
        data: {
          approvedByRef: actorRef,
          createdByRef: actorRef,
          effectiveAt: new Date(),
          expiresAt: input.expiresAt,
          identitySubjectId: identity.id,
          reason: 'Initial controlled authorization bootstrap.',
          roleId: role.id,
          scopes: {
            create: {
              scopeRef: 'global',
              scopeType: WorkforceScopeType.GLOBAL,
            },
          },
        },
      });
      await transaction.workforceEntitlementRevision.upsert({
        create: { identitySubjectId: identity.id, revision: 1 },
        update: { revision: { increment: 1 } },
        where: { identitySubjectId: identity.id },
      });
      const evidence: Prisma.InputJsonValue = {
        assignmentId: assignment.id,
        bootstrapRoleKey: BOOTSTRAP_ROLE_KEY,
      };
      await transaction.auditEvent.create({
        data: {
          action: 'authorization.bootstrap-administrator',
          actorRef,
          actorType: 'system',
          correlationId,
          metadata: evidence,
          outcome: 'succeeded',
          resourceId: identity.id,
          resourceType: 'workforce-identity',
        },
      });
      await transaction.outboxEvent.create({
        data: {
          aggregateId: identity.id,
          aggregateType: 'workforce-identity',
          correlationId,
          eventType: 'workforce.authorization.bootstrap-administrator.v1',
          eventVersion: 1,
          payload: evidence,
        },
      });
    }
  });

  process.stdout.write(
    'Created two initial workforce authorization administrators. OIDC subjects were not logged.\n',
  );
}

async function main(): Promise<void> {
  if (process.env.VFBIZ_AUTHORIZATION_BOOTSTRAP_ACK !== BOOTSTRAP_ACK) {
    throw new Error(
      `Set VFBIZ_AUTHORIZATION_BOOTSTRAP_ACK=${BOOTSTRAP_ACK} to authorize this controlled one-time operation.`,
    );
  }
  const databaseUrl = requiredEnvironment('VFBIZ_DATABASE_URL');
  const prisma = new PrismaClient({ adapter: new PrismaPg(databaseUrl) });
  try {
    await prisma.$connect();
    await bootstrap(prisma, {
      catalog: await loadCatalog(),
      expiresAt: assignmentExpiry(new Date()),
      issuer: requiredEnvironment('VFBIZ_BOOTSTRAP_WORKFORCE_ISSUER'),
      subjects: administratorSubjects(),
    });
  } finally {
    await prisma.$disconnect();
  }
}

void main().catch((error: unknown) => {
  process.stderr.write(
    `${error instanceof Error ? (error.stack ?? error.message) : String(error)}\n`,
  );
  process.exitCode = 1;
});
