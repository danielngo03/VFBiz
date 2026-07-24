import { createHash } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import {
  CustomerGarageEntrySource,
  CustomerGarageEntryStatus,
  CustomerProfileStatus,
} from '../../../../generated/prisma/enums';
import { PrismaService } from '../../../../platform/database/prisma.service';
import { isRetryableTransactionError } from '../../../../platform/database/retryable-transaction-error';
import {
  CustomerGarageRepository,
  type CreateGarageEntryInput,
  type UpdateGarageEntryInput,
} from '../../application/ports/customer-garage.repository';
import {
  CustomerGarageEntryNotFoundError,
  CustomerGarageConcurrentModificationError,
  CustomerGarageIdempotencyConflictError,
  CustomerGaragePrimaryInvariantError,
  CustomerGarageVersionConflictError,
  type CustomerGarageEntryView,
} from '../../domain/customer-garage';

const garageSelection = {
  claimedVehicleVariantId: true,
  createdAt: true,
  id: true,
  isPrimary: true,
  nickname: true,
  source: true,
  status: true,
  updatedAt: true,
  version: true,
} as const;
const MAX_SERIALIZABLE_ATTEMPTS = 3;

type GaragePersistence = Pick<
  PrismaService,
  'customerGarageEntry' | 'customerProfile'
>;

function hash(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex');
}

function createRequestHash(input: CreateGarageEntryInput): string {
  return hash(
    JSON.stringify({
      claimedVehicleVariantId: input.claimedVehicleVariantId,
      isPrimary: input.isPrimary,
      nickname: input.nickname,
    }),
  );
}

function toView(record: {
  claimedVehicleVariantId: string;
  createdAt: Date;
  id: string;
  isPrimary: boolean;
  nickname: string | null;
  source: CustomerGarageEntrySource;
  status: CustomerGarageEntryStatus;
  updatedAt: Date;
  version: number;
}): CustomerGarageEntryView {
  return {
    claimedVehicleVariantId: record.claimedVehicleVariantId,
    createdAt: record.createdAt,
    id: record.id,
    isPrimary: record.isPrimary,
    nickname: record.nickname,
    ownershipStatus: 'unverified',
    source:
      record.source === CustomerGarageEntrySource.IMPORTED
        ? 'imported'
        : 'self-reported',
    status: record.status.toLowerCase() as 'active' | 'archived',
    updatedAt: record.updatedAt,
    version: record.version,
  };
}

@Injectable()
export class PrismaCustomerGarageRepository extends CustomerGarageRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async list(
    principal: AccessPrincipal,
  ): Promise<readonly CustomerGarageEntryView[]> {
    const profileId = await this.profileId(principal);
    const records = await this.prisma.customerGarageEntry.findMany({
      orderBy: [{ isPrimary: 'desc' }, { createdAt: 'asc' }],
      select: garageSelection,
      where: {
        customerProfileId: profileId,
        status: CustomerGarageEntryStatus.ACTIVE,
      },
    });
    return records.map(toView);
  }

  async create(
    input: CreateGarageEntryInput,
  ): Promise<CustomerGarageEntryView> {
    const profileId = await this.profileId(input.principal);
    const idempotencyKeyHash = hash(input.idempotencyKey);
    const requestHash = createRequestHash(input);

    for (let attempt = 1; attempt <= MAX_SERIALIZABLE_ATTEMPTS; attempt += 1) {
      try {
        const created = await this.prisma.$transaction(
          async (transaction) => {
            const activeProfileId = await this.profileId(
              input.principal,
              transaction,
            );
            if (activeProfileId !== profileId) {
              throw new CustomerGarageEntryNotFoundError();
            }
            const activeCount = await transaction.customerGarageEntry.count({
              where: {
                customerProfileId: profileId,
                status: CustomerGarageEntryStatus.ACTIVE,
              },
            });
            const isPrimary = input.isPrimary || activeCount === 0;
            if (isPrimary) {
              await transaction.customerGarageEntry.updateMany({
                data: { isPrimary: false, version: { increment: 1 } },
                where: {
                  customerProfileId: profileId,
                  isPrimary: true,
                  status: CustomerGarageEntryStatus.ACTIVE,
                },
              });
            }
            const record = await transaction.customerGarageEntry.create({
              data: {
                claimedVehicleVariantId: input.claimedVehicleVariantId,
                createIdempotencyKeyHash: idempotencyKeyHash,
                createRequestHash: requestHash,
                customerProfileId: profileId,
                isPrimary,
                nickname: input.nickname,
                source: CustomerGarageEntrySource.SELF_REPORTED,
              },
              select: garageSelection,
            });
            await transaction.auditEvent.create({
              data: {
                action: 'customer.garage.entry.created',
                actorRef: profileId,
                actorType: 'customer',
                correlationId: input.correlationId,
                metadata: {
                  isPrimary: record.isPrimary,
                  source: 'self-reported',
                  variantId: record.claimedVehicleVariantId,
                  version: record.version,
                },
                outcome: 'accepted',
                resourceId: record.id,
                resourceType: 'customer_garage_entry',
              },
            });
            await transaction.outboxEvent.create({
              data: {
                aggregateId: record.id,
                aggregateType: 'customer_garage_entry',
                correlationId: input.correlationId,
                eventType: 'customer.garage.entry.created.v1',
                eventVersion: 1,
                payload: {
                  entryId: record.id,
                  isPrimary: record.isPrimary,
                  variantId: record.claimedVehicleVariantId,
                  version: record.version,
                },
              },
            });
            return record;
          },
          { isolationLevel: 'Serializable' },
        );
        return toView(created);
      } catch (error) {
        const raced = await this.findReplayByHash(
          profileId,
          idempotencyKeyHash,
          requestHash,
        );
        if (raced !== null) return raced;
        if (
          !isRetryableTransactionError(error) ||
          attempt === MAX_SERIALIZABLE_ATTEMPTS
        ) {
          if (isRetryableTransactionError(error)) {
            throw new CustomerGarageConcurrentModificationError();
          }
          throw error;
        }
      }
    }
    throw new CustomerGarageConcurrentModificationError();
  }

  async findCreateReplay(
    input: CreateGarageEntryInput,
  ): Promise<CustomerGarageEntryView | null> {
    const profileId = await this.profileId(input.principal);
    return this.findReplayByHash(
      profileId,
      hash(input.idempotencyKey),
      createRequestHash(input),
    );
  }

  async update(
    input: UpdateGarageEntryInput,
  ): Promise<CustomerGarageEntryView> {
    const updated = await this.withSerializableRetry(() =>
      this.prisma.$transaction(
        async (transaction) => {
          const profileId = await this.profileId(input.principal, transaction);
          const current = await this.entry(
            transaction,
            profileId,
            input.entryId,
          );
          if (current.isPrimary && input.isPrimary === false) {
            throw new CustomerGaragePrimaryInvariantError();
          }
          if (input.isPrimary === true && !current.isPrimary) {
            await transaction.customerGarageEntry.updateMany({
              data: { isPrimary: false, version: { increment: 1 } },
              where: {
                customerProfileId: profileId,
                isPrimary: true,
                status: CustomerGarageEntryStatus.ACTIVE,
              },
            });
          }
          const result = await transaction.customerGarageEntry.updateMany({
            data: {
              ...(input.isPrimary !== undefined && {
                isPrimary: input.isPrimary,
              }),
              ...(input.nickname !== undefined && { nickname: input.nickname }),
              version: { increment: 1 },
            },
            where: {
              customerProfileId: profileId,
              id: input.entryId,
              status: CustomerGarageEntryStatus.ACTIVE,
              version: input.expectedVersion,
            },
          });
          if (result.count !== 1) {
            throw new CustomerGarageVersionConflictError();
          }
          const record =
            await transaction.customerGarageEntry.findUniqueOrThrow({
              select: garageSelection,
              where: { id: input.entryId },
            });
          const changedFields = [
            input.isPrimary !== undefined && 'isPrimary',
            input.nickname !== undefined && 'nickname',
          ].filter((field): field is string => field !== false);
          await transaction.auditEvent.create({
            data: {
              action: 'customer.garage.entry.updated',
              actorRef: profileId,
              actorType: 'customer',
              correlationId: input.correlationId,
              metadata: {
                changedFields,
                isPrimary: record.isPrimary,
                version: record.version,
              },
              outcome: 'accepted',
              resourceId: record.id,
              resourceType: 'customer_garage_entry',
            },
          });
          await transaction.outboxEvent.create({
            data: {
              aggregateId: record.id,
              aggregateType: 'customer_garage_entry',
              correlationId: input.correlationId,
              eventType: 'customer.garage.entry.updated.v1',
              eventVersion: 1,
              payload: {
                changedFields,
                entryId: record.id,
                isPrimary: record.isPrimary,
                version: record.version,
              },
            },
          });
          return record;
        },
        { isolationLevel: 'Serializable' },
      ),
    );
    return toView(updated);
  }

  async archive(
    principal: AccessPrincipal,
    correlationId: string,
    entryId: string,
    expectedVersion: number,
  ): Promise<CustomerGarageEntryView> {
    const archived = await this.withSerializableRetry(() =>
      this.prisma.$transaction(
        async (transaction) => {
          const profileId = await this.profileId(principal, transaction);
          const current = await this.entry(transaction, profileId, entryId);
          if (current.status === CustomerGarageEntryStatus.ARCHIVED) {
            return current;
          }
          const result = await transaction.customerGarageEntry.updateMany({
            data: {
              isPrimary: false,
              status: CustomerGarageEntryStatus.ARCHIVED,
              version: { increment: 1 },
            },
            where: {
              customerProfileId: profileId,
              id: entryId,
              status: CustomerGarageEntryStatus.ACTIVE,
              version: expectedVersion,
            },
          });
          if (result.count !== 1) {
            throw new CustomerGarageVersionConflictError();
          }
          if (current.isPrimary) {
            const replacement = await transaction.customerGarageEntry.findFirst(
              {
                orderBy: { createdAt: 'asc' },
                select: { id: true },
                where: {
                  customerProfileId: profileId,
                  id: { not: entryId },
                  status: CustomerGarageEntryStatus.ACTIVE,
                },
              },
            );
            if (replacement !== null) {
              await transaction.customerGarageEntry.update({
                data: { isPrimary: true, version: { increment: 1 } },
                where: { id: replacement.id },
              });
            }
          }
          const record =
            await transaction.customerGarageEntry.findUniqueOrThrow({
              select: garageSelection,
              where: { id: entryId },
            });
          await transaction.auditEvent.create({
            data: {
              action: 'customer.garage.entry.archived',
              actorRef: profileId,
              actorType: 'customer',
              correlationId,
              metadata: {
                wasPrimary: current.isPrimary,
                version: record.version,
              },
              outcome: 'accepted',
              resourceId: record.id,
              resourceType: 'customer_garage_entry',
            },
          });
          await transaction.outboxEvent.create({
            data: {
              aggregateId: record.id,
              aggregateType: 'customer_garage_entry',
              correlationId,
              eventType: 'customer.garage.entry.archived.v1',
              eventVersion: 1,
              payload: {
                entryId: record.id,
                wasPrimary: current.isPrimary,
                version: record.version,
              },
            },
          });
          return record;
        },
        { isolationLevel: 'Serializable' },
      ),
    );
    return toView(archived);
  }

  private async profileId(
    principal: AccessPrincipal,
    client: GaragePersistence = this.prisma,
  ): Promise<string> {
    if (principal.realm !== 'customer') {
      throw new CustomerGarageEntryNotFoundError();
    }
    const profile = await client.customerProfile.findFirst({
      select: { id: true },
      where: {
        identitySubject: {
          issuer: principal.issuer,
          realm: 'customer',
          status: 'active',
          subject: principal.subject,
        },
        status: CustomerProfileStatus.ACTIVE,
      },
    });
    if (profile === null) throw new CustomerGarageEntryNotFoundError();
    return profile.id;
  }

  private async entry(
    client: GaragePersistence,
    customerProfileId: string,
    id: string,
  ) {
    const record = await client.customerGarageEntry.findFirst({
      where: { customerProfileId, id },
    });
    if (record === null) throw new CustomerGarageEntryNotFoundError();
    return record;
  }

  private async findReplayByHash(
    customerProfileId: string,
    idempotencyKeyHash: string,
    requestHash: string,
  ): Promise<CustomerGarageEntryView | null> {
    const existing = await this.prisma.customerGarageEntry.findUnique({
      where: {
        customerProfileId_createIdempotencyKeyHash: {
          createIdempotencyKeyHash: idempotencyKeyHash,
          customerProfileId,
        },
      },
    });
    if (existing === null) return null;
    if (existing.createRequestHash !== requestHash) {
      throw new CustomerGarageIdempotencyConflictError();
    }
    return toView(existing);
  }

  private async withSerializableRetry<T>(
    operation: () => Promise<T>,
  ): Promise<T> {
    for (let attempt = 1; attempt <= MAX_SERIALIZABLE_ATTEMPTS; attempt += 1) {
      try {
        return await operation();
      } catch (error) {
        if (
          !isRetryableTransactionError(error) ||
          attempt === MAX_SERIALIZABLE_ATTEMPTS
        ) {
          if (isRetryableTransactionError(error)) {
            throw new CustomerGarageConcurrentModificationError();
          }
          throw error;
        }
      }
    }
    throw new CustomerGarageConcurrentModificationError();
  }
}
