import { createHash } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { PrismaService } from '../../../../platform/database/prisma.service';
import { isRetryableTransactionError } from '../../../../platform/database/retryable-transaction-error';
import {
  CustomerAccountRepository,
  type CreateCustomerDataRequestInput,
  type RecordConsentInput,
  type UpdateCustomerProfileInput,
} from '../../application/ports/customer-account.repository';
import {
  CustomerConsentBatchValidationError,
  CustomerConsentPolicyUnavailableError,
  CustomerDataRequestNotFoundError,
  CustomerIdempotencyConflictError,
  CustomerProfileUnavailableError,
  CustomerProfileVersionConflictError,
  type CurrentConsentView,
  type CustomerDataRequestView,
  type CustomerProfileView,
  DSAR_TARGET_SET_REVISION,
  dsarTargetPlan,
} from '../../domain/customer-account';
import {
  ConsentState,
  ConsentPolicyState,
  CustomerDataRequestStatus,
  CustomerDataRequestType,
  CustomerProfileStatus,
  CustomerRequestSource,
} from '../../../../generated/prisma/enums';

const MAX_SERIALIZABLE_ATTEMPTS = 3;

const profileSelection = {
  communicationEmail: true,
  communicationPush: true,
  communicationSms: true,
  displayName: true,
  locale: true,
  market: true,
  timezone: true,
  updatedAt: true,
  version: true,
} as const;

type ProfileRecord = {
  readonly communicationEmail: boolean;
  readonly communicationPush: boolean;
  readonly communicationSms: boolean;
  readonly displayName: string | null;
  readonly locale: string;
  readonly market: string;
  readonly timezone: string;
  readonly updatedAt: Date;
  readonly version: number;
};

function toProfileView(record: ProfileRecord): CustomerProfileView {
  return {
    communicationPreferences: {
      email: record.communicationEmail,
      push: record.communicationPush,
      sms: record.communicationSms,
    },
    displayName: record.displayName,
    locale: record.locale as CustomerProfileView['locale'],
    market: record.market as CustomerProfileView['market'],
    timezone: record.timezone,
    updatedAt: record.updatedAt,
    version: record.version,
  };
}

function sha256(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex');
}

function samePrincipal(left: AccessPrincipal, right: AccessPrincipal): boolean {
  return (
    left.issuer === right.issuer &&
    left.realm === right.realm &&
    left.subject === right.subject
  );
}

type CustomerAccountReader = Pick<
  PrismaService,
  'consentEvent' | 'customerProfile'
>;

@Injectable()
export class PrismaCustomerAccountRepository extends CustomerAccountRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async provisionProfile(
    principal: AccessPrincipal,
  ): Promise<CustomerProfileView> {
    const record = await this.withSerializableRetry(() =>
      this.prisma.$transaction(
        async (transaction) => {
          const identity = await transaction.identitySubject.upsert({
            create: {
              issuer: principal.issuer,
              realm: principal.realm,
              subject: principal.subject,
            },
            update: {},
            where: {
              issuer_subject: {
                issuer: principal.issuer,
                subject: principal.subject,
              },
            },
          });
          if (
            identity.realm !== 'customer' ||
            identity.status !== 'active' ||
            principal.realm !== 'customer'
          ) {
            throw new CustomerProfileUnavailableError();
          }
          return transaction.customerProfile.upsert({
            create: { identitySubjectId: identity.id },
            select: profileSelection,
            update: {},
            where: { identitySubjectId: identity.id },
          });
        },
        { isolationLevel: 'Serializable' },
      ),
    );
    return toProfileView(record);
  }

  async updateProfile(
    input: UpdateCustomerProfileInput,
  ): Promise<CustomerProfileView> {
    const preferences = input.communicationPreferences;
    const changedFields = [
      input.displayName !== undefined && 'displayName',
      input.locale !== undefined && 'locale',
      input.market !== undefined && 'market',
      input.timezone !== undefined && 'timezone',
      preferences?.email !== undefined && 'communicationPreferences.email',
      preferences?.push !== undefined && 'communicationPreferences.push',
      preferences?.sms !== undefined && 'communicationPreferences.sms',
    ].filter((field): field is string => field !== false);
    const updated = await this.withSerializableRetry(() =>
      this.prisma.$transaction(
        async (transaction) => {
          const profile = await this.findActiveProfile(
            input.principal,
            transaction,
          );
          const result = await transaction.customerProfile.updateMany({
            data: {
              ...(input.displayName !== undefined && {
                displayName: input.displayName,
              }),
              ...(input.locale !== undefined && { locale: input.locale }),
              ...(input.market !== undefined && { market: input.market }),
              ...(input.timezone !== undefined && {
                timezone: input.timezone,
              }),
              ...(preferences?.email !== undefined && {
                communicationEmail: preferences.email,
              }),
              ...(preferences?.push !== undefined && {
                communicationPush: preferences.push,
              }),
              ...(preferences?.sms !== undefined && {
                communicationSms: preferences.sms,
              }),
              version: { increment: 1 },
            },
            where: {
              id: profile.id,
              identitySubject: {
                issuer: input.principal.issuer,
                realm: 'customer',
                status: 'active',
                subject: input.principal.subject,
              },
              status: CustomerProfileStatus.ACTIVE,
              version: input.expectedVersion,
            },
          });
          if (result.count !== 1) {
            await this.findActiveProfile(input.principal, transaction);
            throw new CustomerProfileVersionConflictError();
          }
          const record = await transaction.customerProfile.findUniqueOrThrow({
            select: profileSelection,
            where: { id: profile.id },
          });
          await transaction.auditEvent.create({
            data: {
              action: 'customer.profile.updated',
              actorRef: profile.id,
              actorType: 'customer',
              correlationId: input.correlationId,
              metadata: {
                changedFields,
                resultingVersion: record.version,
              },
              outcome: 'accepted',
              resourceId: profile.id,
              resourceType: 'customer_profile',
            },
          });
          await transaction.outboxEvent.create({
            data: {
              aggregateId: profile.id,
              aggregateType: 'customer_profile',
              correlationId: input.correlationId,
              eventType: 'customer.profile.updated.v1',
              eventVersion: 1,
              payload: {
                changedFields,
                version: record.version,
              },
            },
          });
          return record;
        },
        { isolationLevel: 'Serializable' },
      ),
    );
    return toProfileView(updated);
  }

  async listCurrentConsents(
    principal: AccessPrincipal,
  ): Promise<readonly CurrentConsentView[]> {
    const profile = await this.findActiveProfile(principal);
    return this.listCurrentConsentsForProfile(this.prisma, profile.id);
  }

  async recordConsents(
    input: readonly RecordConsentInput[],
  ): Promise<readonly CurrentConsentView[]> {
    if (input.length === 0) return [];
    this.assertConsentBatch(input);
    const records = input.map((event) => ({
      ...event,
      idempotencyKeyHash: sha256(event.idempotencyKey),
      requestHash: sha256(
        JSON.stringify({
          policyVersion: event.policyVersion,
          purpose: event.purpose,
          state: event.state,
        }),
      ),
    }));

    return this.withSerializableRetry(() =>
      this.prisma.$transaction(
        async (transaction) => {
          const profile = await this.findActiveProfile(
            input[0].principal,
            transaction,
          );
          const now = new Date();
          const policies = await transaction.consentPolicy.findMany({
            select: { policyVersion: true, purpose: true },
            where: {
              AND: [
                {
                  OR: records.map((record) => ({
                    policyVersion: record.policyVersion,
                    purpose: record.purpose,
                  })),
                },
                { OR: [{ expiresAt: null }, { expiresAt: { gt: now } }] },
              ],
              approvedAt: { lte: now, not: null },
              approvedByRef: { not: null },
              approvalEvidenceRef: { not: null },
              effectiveAt: { lte: now },
              state: ConsentPolicyState.ACTIVE,
            },
          });
          if (
            policies.length !== records.length ||
            records.some(
              (record) =>
                !policies.some(
                  (policy) =>
                    policy.purpose === record.purpose &&
                    policy.policyVersion === record.policyVersion,
                ),
            )
          ) {
            throw new CustomerConsentPolicyUnavailableError();
          }
          const existing = await transaction.consentEvent.findMany({
            select: {
              idempotencyKeyHash: true,
              purpose: true,
              requestHash: true,
            },
            where: {
              OR: records.map((record) => ({
                customerProfileId: profile.id,
                idempotencyKeyHash: record.idempotencyKeyHash,
                purpose: record.purpose,
              })),
            },
          });
          this.assertConsentReplay(records, existing);

          if (existing.length === 0) {
            await transaction.consentEvent.createMany({
              data: records.map((event) => ({
                correlationId: event.correlationId,
                customerProfileId: profile.id,
                idempotencyKeyHash: event.idempotencyKeyHash,
                policyVersion: event.policyVersion,
                purpose: event.purpose,
                requestHash: event.requestHash,
                source: event.source.toUpperCase() as CustomerRequestSource,
                state: event.state.toUpperCase() as ConsentState,
              })),
              skipDuplicates: false,
            });
            const correlationId = input[0].correlationId;
            const changes = records.map((event) => ({
              policyVersion: event.policyVersion,
              purpose: event.purpose,
              state: event.state,
            }));
            await transaction.auditEvent.create({
              data: {
                action: 'customer.consent.changed',
                actorRef: profile.id,
                actorType: 'customer',
                correlationId,
                metadata: { changes },
                outcome: 'accepted',
                resourceId: profile.id,
                resourceType: 'customer_profile',
              },
            });
            await transaction.outboxEvent.create({
              data: {
                aggregateId: profile.id,
                aggregateType: 'customer_profile',
                correlationId,
                eventType: 'customer.consent.changed.v1',
                eventVersion: 1,
                payload: { changes },
              },
            });
          }

          return this.listCurrentConsentsForProfile(transaction, profile.id);
        },
        { isolationLevel: 'Serializable' },
      ),
    );
  }

  async createDataRequest(
    input: CreateCustomerDataRequestInput,
  ): Promise<CustomerDataRequestView> {
    const idempotencyKeyHash = sha256(input.idempotencyKey);
    const requestHash = sha256(input.type);
    return this.withSerializableRetry(() =>
      this.prisma.$transaction(
        async (transaction) => {
          const profile = await this.findActiveProfile(
            input.principal,
            transaction,
          );
          const uniqueKey = {
            customerProfileId: profile.id,
            idempotencyKeyHash,
            requestType: input.type.toUpperCase() as CustomerDataRequestType,
          };
          const existing = await transaction.customerDataRequest.findUnique({
            where: {
              customerProfileId_requestType_idempotencyKeyHash: uniqueKey,
            },
          });
          if (existing !== null) {
            if (existing.requestHash !== requestHash) {
              throw new CustomerIdempotencyConflictError();
            }
            return this.toDataRequestView(existing);
          }
          const created = await transaction.customerDataRequest.create({
            data: {
              correlationId: input.correlationId,
              customerProfileId: profile.id,
              events: {
                create: {
                  correlationId: input.correlationId,
                  eventType: 'request.created',
                  outcomeCode: 'accepted',
                },
              },
              idempotencyKeyHash,
              nextReconcileAt: new Date(),
              policyRevision: 'dsar-policy-v1',
              requestHash,
              requestType: uniqueKey.requestType,
              source: input.source.toUpperCase() as CustomerRequestSource,
              targetSetRevision: DSAR_TARGET_SET_REVISION,
              targets: {
                create: dsarTargetPlan(input.type).map((target) => ({
                  phase: target.phase,
                  targetKey: target.key,
                  targetVersion: target.version,
                })),
              },
            },
          });
          await transaction.auditEvent.create({
            data: {
              action: 'customer.data_request.created',
              actorRef: profile.id,
              actorType: 'customer',
              correlationId: input.correlationId,
              metadata: {
                requestType: input.type,
                targetSetRevision: DSAR_TARGET_SET_REVISION,
              },
              outcome: 'accepted',
              resourceId: created.id,
              resourceType: 'customer_data_request',
            },
          });
          await transaction.outboxEvent.create({
            data: {
              aggregateId: created.id,
              aggregateType: 'customer_data_request',
              correlationId: input.correlationId,
              eventType: 'customer.data_request.requested.v1',
              eventVersion: 1,
              payload: {
                requestId: created.id,
                requestType: input.type,
                targetSetRevision: DSAR_TARGET_SET_REVISION,
              },
            },
          });
          return this.toDataRequestView(created);
        },
        { isolationLevel: 'Serializable' },
      ),
    );
  }

  async listDataRequests(
    principal: AccessPrincipal,
  ): Promise<readonly CustomerDataRequestView[]> {
    const profile = await this.findActiveProfile(principal);
    const requests = await this.prisma.customerDataRequest.findMany({
      orderBy: { requestedAt: 'desc' },
      where: { customerProfileId: profile.id },
    });
    return requests.map((request) => this.toDataRequestView(request));
  }

  async getDataRequest(
    principal: AccessPrincipal,
    requestId: string,
  ): Promise<CustomerDataRequestView> {
    const profile = await this.findActiveProfile(principal);
    const request = await this.prisma.customerDataRequest.findFirst({
      where: { customerProfileId: profile.id, id: requestId },
    });
    if (request === null) throw new CustomerDataRequestNotFoundError();
    return this.toDataRequestView(request);
  }

  private assertConsentBatch(input: readonly RecordConsentInput[]): void {
    const purposes = new Set<string>();
    const principal = input[0].principal;
    for (const event of input) {
      if (
        purposes.has(event.purpose) ||
        !samePrincipal(principal, event.principal)
      ) {
        throw new CustomerConsentBatchValidationError();
      }
      purposes.add(event.purpose);
    }
  }

  private assertConsentReplay(
    requested: readonly {
      idempotencyKeyHash: string;
      purpose: string;
      requestHash: string;
    }[],
    existing: readonly {
      idempotencyKeyHash: string;
      purpose: string;
      requestHash: string;
    }[],
  ): void {
    if (existing.length !== 0 && existing.length !== requested.length) {
      throw new CustomerIdempotencyConflictError();
    }
    for (const event of existing) {
      const match = requested.find(
        (record) =>
          record.idempotencyKeyHash === event.idempotencyKeyHash &&
          record.purpose === event.purpose,
      );
      if (match?.requestHash !== event.requestHash) {
        throw new CustomerIdempotencyConflictError();
      }
    }
  }

  private async listCurrentConsentsForProfile(
    client: CustomerAccountReader,
    customerProfileId: string,
  ): Promise<readonly CurrentConsentView[]> {
    const events = await client.consentEvent.findMany({
      orderBy: [{ purpose: 'asc' }, { eventSequence: 'desc' }],
      select: {
        occurredAt: true,
        policyVersion: true,
        purpose: true,
        source: true,
        state: true,
      },
      where: { customerProfileId },
    });
    const latest = new Map<string, CurrentConsentView>();
    for (const event of events) {
      if (latest.has(event.purpose)) continue;
      latest.set(event.purpose, {
        occurredAt: event.occurredAt,
        policyVersion: event.policyVersion,
        purpose: event.purpose as CurrentConsentView['purpose'],
        source: event.source
          .toLowerCase()
          .replaceAll('-', '_') as CurrentConsentView['source'],
        state: event.state.toLowerCase() as CurrentConsentView['state'],
      });
    }
    return [...latest.values()];
  }

  private async findActiveProfile(
    principal: AccessPrincipal,
    client: CustomerAccountReader = this.prisma,
  ) {
    if (principal.realm !== 'customer') {
      throw new CustomerProfileUnavailableError();
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
    if (profile === null) throw new CustomerProfileUnavailableError();
    return profile;
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
          throw error;
        }
      }
    }
    throw new Error('Serializable transaction retry loop was exhausted.');
  }

  private toDataRequestView(record: {
    completedAt: Date | null;
    id: string;
    requestedAt: Date;
    requestType: CustomerDataRequestType;
    status: CustomerDataRequestStatus;
  }): CustomerDataRequestView {
    return {
      completedAt: record.completedAt,
      id: record.id,
      requestedAt: record.requestedAt,
      status: record.status.toLowerCase() as CustomerDataRequestView['status'],
      type: record.requestType.toLowerCase() as CustomerDataRequestView['type'],
    };
  }
}
