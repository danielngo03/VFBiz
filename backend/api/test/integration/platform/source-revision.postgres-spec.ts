import { ConfigService } from '@nestjs/config';
import {
  DataClassification,
  SourceApprovalState,
  VehicleFactGroup,
  VehicleFactSubjectType,
} from '../../../src/generated/prisma/enums';
import { PrismaService } from '../../../src/platform/database/prisma.service';

const databaseUrl = process.env.VFBIZ_TEST_DATABASE_URL;
const describeWithDatabase =
  databaseUrl === undefined ? describe.skip : describe;

describeWithDatabase('Source revision PostgreSQL governance', () => {
  let prisma: PrismaService;
  const sourceName = 'vehicle-pim-governance-integration';

  beforeAll(async () => {
    prisma = new PrismaService(
      new ConfigService({
        NODE_ENV: 'test',
        VFBIZ_DATABASE_URL: databaseUrl,
      }),
    );
    await prisma.$connect();
  });

  afterAll(async () => prisma.$disconnect());

  beforeEach(async () => {
    await prisma.vehicleFactProvenanceBinding.deleteMany({
      where: { sourceRevision: { source: sourceName } },
    });
    await prisma.vehicleCatalogRelease.deleteMany({
      where: { sourceRevision: { source: sourceName } },
    });
    await prisma.sourceRevision.deleteMany({ where: { source: sourceName } });
  });

  function approvedSource(revision: string) {
    return {
      approvalEvidenceRef: `evidence://vehicle-data/${revision}`,
      approvalState: SourceApprovalState.APPROVED,
      approvedAt: new Date('2026-07-23T10:00:00.000Z'),
      approvedByRef: 'data-owner-2',
      checksum: 'a'.repeat(64),
      classification: DataClassification.INTERNAL,
      effectiveAt: new Date('2026-07-23T00:00:00.000Z'),
      expiresAt: new Date('2026-07-24T00:00:00.000Z'),
      freshnessTtlSeconds: 86_400,
      licenseId: 'PROPRIETARY-VINFAST-APPROVED',
      observedAt: new Date('2026-07-23T09:00:00.000Z'),
      ownerRef: 'vehicle-data-owner',
      permittedPurposes: ['vehicle-catalog'],
      provenanceUri: `urn:vfbiz:source:pim:${revision}`,
      revision,
      source: sourceName,
      submittedByRef: 'vehicle-data-operator-1',
    };
  }

  it('rejects an approved source that still contains placeholder evidence', async () => {
    await expect(
      prisma.sourceRevision.create({
        data: {
          ...approvedSource('invalid-placeholder'),
          licenseId: 'UNVERIFIED',
        },
      }),
    ).rejects.toBeDefined();
  });

  it('pins one governed source per subject and fact group', async () => {
    const source = await prisma.sourceRevision.create({
      data: approvedSource('release-42'),
    });
    const release = await prisma.vehicleCatalogRelease.create({
      data: {
        effectiveAt: new Date('2026-07-23T00:00:00.000Z'),
        market: 'VN',
        releaseVersion: 'governance-integration-42',
        sourceRevisionId: source.id,
        submittedByRef: 'integration-product-data-operator',
      },
    });
    const binding = {
      catalogReleaseId: release.id,
      factGroup: VehicleFactGroup.IDENTITY_COMMERCIAL,
      sourceRevisionId: source.id,
      subjectRef: release.id,
      subjectType: VehicleFactSubjectType.RELEASE,
    };

    await prisma.vehicleFactProvenanceBinding.create({ data: binding });
    await expect(
      prisma.vehicleFactProvenanceBinding.create({ data: binding }),
    ).rejects.toBeDefined();
  });
});
