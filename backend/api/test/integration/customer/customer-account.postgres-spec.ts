import { ConfigService } from '@nestjs/config';
import { randomUUID } from 'node:crypto';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';
import { PrismaService } from '../../../src/platform/database/prisma.service';
import { CustomerDataRequestNotFoundError } from '../../../src/modules/customer/domain/customer-account';
import { CustomerProfileUnavailableError } from '../../../src/modules/customer/domain/customer-account';
import { PrismaCustomerAccountRepository } from '../../../src/modules/customer/infrastructure/persistence/prisma-customer-account.repository';
import { PrismaCustomerGarageRepository } from '../../../src/modules/customer/infrastructure/persistence/prisma-customer-garage.repository';
import { CustomerGarageEntryNotFoundError } from '../../../src/modules/customer/domain/customer-garage';

const databaseUrl = process.env.VFBIZ_TEST_DATABASE_URL;
const describeWithDatabase =
  databaseUrl === undefined ? describe.skip : describe;

describeWithDatabase('Customer account PostgreSQL integration', () => {
  let prisma: PrismaService;
  let repository: PrismaCustomerAccountRepository;
  let garageRepository: PrismaCustomerGarageRepository;
  let vehicleVariantId: string;
  const issuer = 'https://id.example/realms/customer-consent-integration';
  const principal: AccessPrincipal = {
    authenticationContext: null,
    authenticationMethods: [],
    audience: ['vfbiz-customer-api'],
    authorizedParty: 'vfbiz-customer-bff',
    issuer,
    realm: 'customer',
    scopes: ['consent:read', 'consent:write'],
    sessionId: 'customer-consent-session',
    subject: 'customer-consent-subject',
  };

  beforeAll(async () => {
    prisma = new PrismaService(
      new ConfigService({
        NODE_ENV: 'test',
        VFBIZ_DATABASE_URL: databaseUrl,
      }),
    );
    await prisma.$connect();
    repository = new PrismaCustomerAccountRepository(prisma);
    garageRepository = new PrismaCustomerGarageRepository(prisma);
    const model = await prisma.vehicleModel.upsert({
      create: {
        brandCode: 'VINFAST',
        modelCode: 'SYNTHETIC-ACCOUNT-INTEGRATION',
        slug: 'synthetic-account-integration',
      },
      update: {},
      where: { slug: 'synthetic-account-integration' },
    });
    const variant = await prisma.vehicleVariant.upsert({
      create: {
        variantCode: 'SYNTHETIC-BASE',
        vehicleModelId: model.id,
      },
      update: {},
      where: {
        vehicleModelId_variantCode: {
          variantCode: 'SYNTHETIC-BASE',
          vehicleModelId: model.id,
        },
      },
    });
    vehicleVariantId = variant.id;
  });

  afterAll(async () => {
    await prisma.customerGarageEntry.deleteMany({
      where: { claimedVehicleVariantId: vehicleVariantId },
    });
    await prisma.vehicleVariant.delete({ where: { id: vehicleVariantId } });
    await prisma.vehicleModel.delete({
      where: { slug: 'synthetic-account-integration' },
    });
    await prisma.$disconnect();
  });

  beforeEach(async () => {
    await prisma.outboxEvent.deleteMany({
      where: { eventType: 'customer.consent.changed.v1' },
    });
    await prisma.auditEvent.deleteMany({
      where: { action: 'customer.consent.changed' },
    });
    await prisma.outboxEvent.deleteMany({
      where: { eventType: 'customer.data_request.requested.v1' },
    });
    await prisma.auditEvent.deleteMany({
      where: { action: 'customer.data_request.created' },
    });
    await prisma.customerDataRequest.deleteMany({
      where: { customerProfile: { identitySubject: { issuer } } },
    });
    await prisma.customerGarageEntry.deleteMany({
      where: { customerProfile: { identitySubject: { issuer } } },
    });
    await prisma.consentEvent.deleteMany({
      where: { customerProfile: { identitySubject: { issuer } } },
    });
    await prisma.consentPolicy.deleteMany({
      where: { policyVersion: { startsWith: 'policy-v' } },
    });
    await prisma.customerProfile.deleteMany({
      where: { identitySubject: { issuer } },
    });
    await prisma.identitySubject.deleteMany({ where: { issuer } });
    await prisma.consentPolicy.create({
      data: {
        approvalEvidenceRef: 'evidence://consent/policy-v1',
        approvedAt: new Date('2026-07-22T00:00:00.000Z'),
        approvedByRef: 'privacy-owner-integration',
        contentChecksum: 'c'.repeat(64),
        effectiveAt: new Date('2026-07-23T00:00:00.000Z'),
        policyVersion: 'policy-v1',
        purpose: 'marketing_email',
        state: 'ACTIVE',
      },
    });
    await repository.provisionProfile(principal);
  });

  function consent(
    idempotencyKey: string,
    policyVersion: string,
    state: 'granted' | 'withdrawn',
  ) {
    return repository.recordConsents([
      {
        correlationId: randomUUID(),
        idempotencyKey,
        policyVersion,
        principal,
        purpose: 'marketing_email',
        source: 'customer_portal',
        state,
      },
    ]);
  }

  it('resolves current consent by database sequence, not timestamp or UUID', async () => {
    await Promise.all([
      consent('consent-concurrent-grant-0001', 'policy-v1', 'granted'),
      consent('consent-concurrent-withdraw-01', 'policy-v1', 'withdrawn'),
    ]);

    const profile = await prisma.customerProfile.findFirstOrThrow({
      select: { id: true },
      where: { identitySubject: { issuer, subject: principal.subject } },
    });
    const newest = await prisma.consentEvent.findFirstOrThrow({
      orderBy: { eventSequence: 'desc' },
      where: {
        customerProfileId: profile.id,
        purpose: 'marketing_email',
      },
    });
    const current = await repository.listCurrentConsents(principal);

    expect(current).toHaveLength(1);
    expect(current[0]?.policyVersion).toBe(newest.policyVersion);
    expect(current[0]?.state).toBe(newest.state.toLowerCase());
  });

  it('replays the same concurrent idempotent request without duplicate events', async () => {
    await Promise.all([
      consent('consent-idempotent-request-001', 'policy-v1', 'granted'),
      consent('consent-idempotent-request-001', 'policy-v1', 'granted'),
    ]);

    const count = await prisma.consentEvent.count({
      where: { customerProfile: { identitySubject: { issuer } } },
    });
    expect(count).toBe(1);
  });

  it('atomically snapshots DSAR targets, event, audit and outbox', async () => {
    const correlationId = randomUUID();
    const input = {
      correlationId,
      idempotencyKey: 'dsar-integration-request-0001',
      principal,
      source: 'customer_portal' as const,
      type: 'delete' as const,
    };

    const [first, replay] = await Promise.all([
      repository.createDataRequest(input),
      repository.createDataRequest(input),
    ]);

    expect(replay.id).toBe(first.id);
    expect(first.completedAt).toBeNull();
    await expect(
      prisma.customerDataRequestTarget.count({
        where: { requestId: first.id },
      }),
    ).resolves.toBe(8);
    await expect(
      prisma.customerDataRequestEvent.count({
        where: { requestId: first.id },
      }),
    ).resolves.toBe(1);
    await expect(
      prisma.auditEvent.count({
        where: {
          action: 'customer.data_request.created',
          resourceId: first.id,
        },
      }),
    ).resolves.toBe(1);
    await expect(
      prisma.outboxEvent.count({
        where: {
          aggregateId: first.id,
          eventType: 'customer.data_request.requested.v1',
        },
      }),
    ).resolves.toBe(1);

    await expect(repository.listDataRequests(principal)).resolves.toEqual([
      expect.objectContaining({ id: first.id, status: 'requested' }),
    ]);

    const otherPrincipal: AccessPrincipal = {
      ...principal,
      sessionId: 'customer-consent-session-other',
      subject: 'customer-consent-subject-other',
    };
    await repository.provisionProfile(otherPrincipal);
    await expect(
      repository.getDataRequest(otherPrincipal, first.id),
    ).rejects.toBeInstanceOf(CustomerDataRequestNotFoundError);
  });

  it('updates profile with audit and outbox in the same transaction', async () => {
    const profile = await repository.provisionProfile(principal);
    const correlationId = randomUUID();
    const updated = await repository.updateProfile({
      communicationPreferences: { email: true },
      correlationId,
      displayName: 'Synthetic Customer',
      expectedVersion: profile.version,
      principal,
    });

    expect(updated.version).toBe(profile.version + 1);
    await expect(
      prisma.auditEvent.count({
        where: { action: 'customer.profile.updated', correlationId },
      }),
    ).resolves.toBe(1);
    await expect(
      prisma.outboxEvent.count({
        where: { eventType: 'customer.profile.updated.v1', correlationId },
      }),
    ).resolves.toBe(1);
  });

  it('fails customer mutations closed after the identity is suspended', async () => {
    const profile = await repository.provisionProfile(principal);
    await prisma.identitySubject.updateMany({
      data: { status: 'suspended' },
      where: { issuer, subject: principal.subject },
    });

    await expect(
      repository.updateProfile({
        correlationId: randomUUID(),
        displayName: 'Must not be written',
        expectedVersion: profile.version,
        principal,
      }),
    ).rejects.toBeInstanceOf(CustomerProfileUnavailableError);
    await expect(
      garageRepository.create({
        claimedVehicleVariantId: vehicleVariantId,
        correlationId: randomUUID(),
        idempotencyKey: 'garage-suspended-customer-0001',
        isPrimary: true,
        nickname: null,
        principal,
      }),
    ).rejects.toBeInstanceOf(CustomerGarageEntryNotFoundError);
  });

  it('writes garage state, audit and outbox atomically', async () => {
    const createCorrelationId = randomUUID();
    const created = await garageRepository.create({
      claimedVehicleVariantId: vehicleVariantId,
      correlationId: createCorrelationId,
      idempotencyKey: 'garage-integration-create-0001',
      isPrimary: true,
      nickname: 'Xe synthetic',
      principal,
    });

    expect(created.ownershipStatus).toBe('unverified');
    await expect(
      prisma.auditEvent.count({
        where: {
          action: 'customer.garage.entry.created',
          correlationId: createCorrelationId,
        },
      }),
    ).resolves.toBe(1);
    await expect(
      prisma.outboxEvent.count({
        where: {
          correlationId: createCorrelationId,
          eventType: 'customer.garage.entry.created.v1',
        },
      }),
    ).resolves.toBe(1);

    const updateCorrelationId = randomUUID();
    const updated = await garageRepository.update({
      correlationId: updateCorrelationId,
      entryId: created.id,
      expectedVersion: created.version,
      nickname: 'Xe gia đình',
      principal,
    });
    expect(updated.version).toBe(created.version + 1);

    const archiveCorrelationId = randomUUID();
    const archived = await garageRepository.archive(
      principal,
      archiveCorrelationId,
      updated.id,
      updated.version,
    );
    expect(archived.status).toBe('archived');
    await expect(
      prisma.outboxEvent.count({
        where: {
          aggregateId: created.id,
          eventType: {
            in: [
              'customer.garage.entry.created.v1',
              'customer.garage.entry.updated.v1',
              'customer.garage.entry.archived.v1',
            ],
          },
        },
      }),
    ).resolves.toBe(3);
  });
});
