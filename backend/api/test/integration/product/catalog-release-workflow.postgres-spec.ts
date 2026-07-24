import { randomUUID } from 'node:crypto';
import { ConfigService } from '@nestjs/config';
import {
  DataClassification,
  SourceApprovalState,
  VehicleCatalogReleaseState,
  VehicleCommercialStatus,
  VehicleFactGroup,
  VehicleFactSubjectType,
} from '../../../src/generated/prisma/enums';
import { PrismaCatalogReleaseWorkflowRepository } from '../../../src/modules/product/infrastructure/persistence/prisma-catalog-release-workflow.repository';
import { PrismaService } from '../../../src/platform/database/prisma.service';

const databaseUrl = process.env.VFBIZ_TEST_DATABASE_URL;
const describeWithDatabase =
  databaseUrl === undefined ? describe.skip : describe;

describeWithDatabase('Catalog release workflow PostgreSQL', () => {
  let prisma: PrismaService;
  let repository: PrismaCatalogReleaseWorkflowRepository;
  const sourceName = 'catalog-release-workflow-integration';
  const createdReleaseIds: string[] = [];
  const createdModelIds: string[] = [];

  beforeAll(async () => {
    prisma = new PrismaService(
      new ConfigService({
        NODE_ENV: 'test',
        VFBIZ_DATABASE_URL: databaseUrl,
      }),
    );
    await prisma.$connect();
    repository = new PrismaCatalogReleaseWorkflowRepository(prisma);
  });

  afterAll(async () => prisma.$disconnect());

  beforeEach(() => {
    createdReleaseIds.length = 0;
    createdModelIds.length = 0;
  });

  afterEach(async () => {
    await prisma.auditEvent.deleteMany({
      where: {
        resourceId: { in: createdReleaseIds },
        resourceType: 'vehicle_catalog_release',
      },
    });
    await prisma.outboxEvent.deleteMany({
      where: {
        aggregateId: { in: createdReleaseIds },
        aggregateType: 'vehicle_catalog_release',
      },
    });
    await prisma.vehicleFactProvenanceBinding.deleteMany({
      where: { catalogReleaseId: { in: createdReleaseIds } },
    });
    await prisma.vehicleVariantRevision.deleteMany({
      where: { catalogReleaseId: { in: createdReleaseIds } },
    });
    await prisma.vehicleModelRevision.deleteMany({
      where: { catalogReleaseId: { in: createdReleaseIds } },
    });
    await prisma.vehicleCatalogRelease.deleteMany({
      where: { id: { in: createdReleaseIds } },
    });
    await prisma.vehicleVariant.deleteMany({
      where: { vehicleModelId: { in: createdModelIds } },
    });
    await prisma.vehicleModel.deleteMany({
      where: { id: { in: createdModelIds } },
    });
    await prisma.sourceRevision.deleteMany({ where: { source: sourceName } });
  });

  async function createReleaseFixture(): Promise<{
    activeReleaseId: string;
    draftReleaseId: string;
  }> {
    const now = new Date('2026-07-24T06:00:00.000Z');
    const source = await prisma.sourceRevision.create({
      data: {
        approvalEvidenceRef: 'evidence://catalog/source-review',
        approvalState: SourceApprovalState.APPROVED,
        approvedAt: new Date('2026-07-24T05:02:00.000Z'),
        approvedByRef: 'source-data-owner',
        checksum: 'b'.repeat(64),
        classification: DataClassification.PUBLIC,
        effectiveAt: new Date('2026-07-24T00:00:00.000Z'),
        expiresAt: new Date('2026-07-25T00:00:00.000Z'),
        freshnessTtlSeconds: 86_400,
        ingestedAt: new Date('2026-07-24T05:01:00.000Z'),
        licenseId: 'PROPRIETARY-APPROVED',
        observedAt: new Date('2026-07-24T05:00:00.000Z'),
        ownerRef: 'catalog-data-owner',
        permittedPurposes: ['vehicle-catalog'],
        provenanceUri: `urn:vfbiz:test:${randomUUID()}`,
        revision: randomUUID(),
        source: sourceName,
        submittedByRef: 'source-data-operator',
      },
    });
    const model = await prisma.vehicleModel.create({
      data: {
        brandCode: `TEST_${randomUUID().slice(0, 32)}`,
        modelCode: `MODEL_${randomUUID()}`,
        slug: `catalog-workflow-${randomUUID()}`,
      },
    });
    const variant = await prisma.vehicleVariant.create({
      data: {
        variantCode: `VARIANT_${randomUUID()}`,
        vehicleModelId: model.id,
      },
    });
    createdModelIds.push(model.id);

    const activeRelease = await prisma.vehicleCatalogRelease.create({
      data: {
        activatedAt: now,
        activatedByRef: 'release-owner',
        approvalEvidenceRef: 'evidence://catalog/release-active',
        approvedAt: new Date('2026-07-24T05:30:00.000Z'),
        approvedByRef: 'catalog-reviewer',
        effectiveAt: new Date('2026-07-24T00:00:00.000Z'),
        market: randomUUID().slice(0, 8).toUpperCase(),
        releaseVersion: `active-${randomUUID()}`,
        revision: 2,
        sourceRevisionId: source.id,
        state: VehicleCatalogReleaseState.ACTIVE,
        submittedByRef: 'catalog-operator',
      },
    });
    const draftRelease = await prisma.vehicleCatalogRelease.create({
      data: {
        effectiveAt: new Date('2026-07-24T00:00:00.000Z'),
        market: activeRelease.market,
        releaseVersion: `draft-${randomUUID()}`,
        sourceRevisionId: source.id,
        submittedByRef: 'catalog-operator',
      },
    });
    createdReleaseIds.push(activeRelease.id, draftRelease.id);

    for (const release of [activeRelease, draftRelease]) {
      await prisma.vehicleModelRevision.create({
        data: {
          canonicalName: 'Integration Test EV',
          catalogReleaseId: release.id,
          category: 'integration-test',
          commercialStatus: VehicleCommercialStatus.ACTIVE,
          vehicleModelId: model.id,
        },
      });
      await prisma.vehicleVariantRevision.create({
        data: {
          canonicalName: 'Integration Test EV Standard',
          catalogReleaseId: release.id,
          commercialStatus: VehicleCommercialStatus.ACTIVE,
          connectorStandards: [],
          extensionData: {},
          specificationSchemaVersion: 'test-v1',
          vehicleVariantId: variant.id,
        },
      });
      await prisma.vehicleFactProvenanceBinding.createMany({
        data: [
          {
            catalogReleaseId: release.id,
            factGroup: VehicleFactGroup.IDENTITY_COMMERCIAL,
            sourceRevisionId: source.id,
            subjectRef: release.id,
            subjectType: VehicleFactSubjectType.RELEASE,
          },
          {
            catalogReleaseId: release.id,
            factGroup: VehicleFactGroup.IDENTITY_COMMERCIAL,
            sourceRevisionId: source.id,
            subjectRef: model.id,
            subjectType: VehicleFactSubjectType.MODEL,
          },
          {
            catalogReleaseId: release.id,
            factGroup: VehicleFactGroup.IDENTITY_COMMERCIAL,
            sourceRevisionId: source.id,
            subjectRef: variant.id,
            subjectType: VehicleFactSubjectType.VARIANT,
          },
        ],
      });
    }
    return {
      activeReleaseId: activeRelease.id,
      draftReleaseId: draftRelease.id,
    };
  }

  it('approves, atomically activates and rolls back releases', async () => {
    const fixture = await createReleaseFixture();
    const now = new Date('2026-07-24T06:00:00.000Z');

    const approved = await repository.approve({
      correlationId: randomUUID(),
      evidenceRef: 'evidence://catalog/release-draft',
      expectedRevision: 0,
      now,
      releaseId: fixture.draftReleaseId,
      reviewerRef: 'catalog-reviewer',
    });
    expect(approved).toMatchObject({ revision: 1, state: 'approved' });

    const active = await repository.activate({
      actorRef: 'release-owner',
      correlationId: randomUUID(),
      expectedRevision: 1,
      now,
      releaseId: fixture.draftReleaseId,
    });
    expect(active).toMatchObject({ revision: 2, state: 'active' });
    expect(
      await prisma.vehicleCatalogRelease.count({
        where: {
          market: active.market,
          state: VehicleCatalogReleaseState.ACTIVE,
        },
      }),
    ).toBe(1);

    const restored = await repository.rollback({
      actorRef: 'release-owner',
      correlationId: randomUUID(),
      expectedCurrentRevision: 2,
      expectedTargetRevision: 3,
      now,
      targetReleaseId: fixture.activeReleaseId,
    });
    expect(restored).toMatchObject({ revision: 4, state: 'active' });
    expect(
      await prisma.vehicleCatalogRelease.count({
        where: {
          market: restored.market,
          state: VehicleCatalogReleaseState.ACTIVE,
        },
      }),
    ).toBe(1);
    expect(
      await prisma.auditEvent.count({
        where: {
          resourceId: { in: createdReleaseIds },
          resourceType: 'vehicle_catalog_release',
        },
      }),
    ).toBe(3);
    expect(
      await prisma.outboxEvent.count({
        where: {
          aggregateId: { in: createdReleaseIds },
          aggregateType: 'vehicle_catalog_release',
        },
      }),
    ).toBe(3);
  });
});
