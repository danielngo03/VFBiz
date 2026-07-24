import { randomUUID } from 'node:crypto';
import { ConfigService } from '@nestjs/config';
import {
  CommercialAnomalyDisposition,
  CommercialAnomalySeverity,
  CommercialChannel,
  CommercialReleaseState,
  DataClassification,
  PriceType,
  PromotionBenefitType,
  PromotionStackingPolicy,
  SourceApprovalState,
  TaxTreatment,
} from '../../../src/generated/prisma/enums';
import { PrismaCommercialDataRepository } from '../../../src/modules/product/infrastructure/persistence/prisma-commercial-data.repository';
import { PrismaCommercialReleaseWorkflowRepository } from '../../../src/modules/product/infrastructure/persistence/prisma-commercial-release-workflow.repository';
import { PrismaService } from '../../../src/platform/database/prisma.service';

const databaseUrl = process.env.VFBIZ_TEST_DATABASE_URL;
const describeWithDatabase =
  databaseUrl === undefined ? describe.skip : describe;

describeWithDatabase('Commercial data PostgreSQL projection', () => {
  let prisma: PrismaService;
  let repository: PrismaCommercialDataRepository;
  let workflow: PrismaCommercialReleaseWorkflowRepository;
  const sourceName = 'commercial-data-integration';
  const releaseIds: string[] = [];
  const modelIds: string[] = [];

  beforeAll(async () => {
    prisma = new PrismaService(
      new ConfigService({
        NODE_ENV: 'test',
        VFBIZ_DATABASE_URL: databaseUrl,
      }),
    );
    await prisma.$connect();
    repository = new PrismaCommercialDataRepository(prisma);
    workflow = new PrismaCommercialReleaseWorkflowRepository(prisma);
  });

  afterAll(async () => prisma.$disconnect());

  afterEach(async () => {
    await prisma.commercialFactAnomaly.deleteMany({
      where: {
        OR: [
          { priceOffer: { commercialReleaseId: { in: releaseIds } } },
          { promotion: { commercialReleaseId: { in: releaseIds } } },
        ],
      },
    });
    await prisma.priceOffer.deleteMany({
      where: { commercialReleaseId: { in: releaseIds } },
    });
    await prisma.promotion.deleteMany({
      where: { commercialReleaseId: { in: releaseIds } },
    });
    await prisma.commercialDataRelease.deleteMany({
      where: { id: { in: releaseIds } },
    });
    await prisma.vehicleVariant.deleteMany({
      where: { vehicleModelId: { in: modelIds } },
    });
    await prisma.vehicleModel.deleteMany({
      where: { id: { in: modelIds } },
    });
    await prisma.sourceRevision.deleteMany({ where: { source: sourceName } });
    releaseIds.length = 0;
    modelIds.length = 0;
  });

  async function createFixture(): Promise<{
    modelId: string;
    offerId: string;
    releaseId: string;
    sourceRevisionId: string;
    variantId: string;
  }> {
    const source = await prisma.sourceRevision.create({
      data: {
        approvalEvidenceRef: 'evidence://commercial/source-review',
        approvalState: SourceApprovalState.APPROVED,
        approvedAt: new Date('2026-07-24T05:02:00.000Z'),
        approvedByRef: 'commercial-data-reviewer',
        checksum: 'c'.repeat(64),
        classification: DataClassification.PUBLIC,
        effectiveAt: new Date('2026-07-24T00:00:00.000Z'),
        expiresAt: new Date('2026-07-25T00:00:00.000Z'),
        freshnessTtlSeconds: 86_400,
        ingestedAt: new Date('2026-07-24T05:01:00.000Z'),
        licenseId: 'PROPRIETARY-APPROVED',
        observedAt: new Date('2026-07-24T05:00:00.000Z'),
        ownerRef: 'commercial-data-owner',
        permittedPurposes: ['vehicle-commercial-data'],
        provenanceUri: `urn:vfbiz:test:${randomUUID()}`,
        revision: randomUUID(),
        source: sourceName,
        submittedByRef: 'commercial-data-operator',
      },
    });
    const model = await prisma.vehicleModel.create({
      data: {
        brandCode: `TEST_${randomUUID().slice(0, 20)}`,
        modelCode: `MODEL_${randomUUID()}`,
        slug: `commercial-${randomUUID()}`,
      },
    });
    const variant = await prisma.vehicleVariant.create({
      data: {
        variantCode: `VARIANT_${randomUUID()}`,
        vehicleModelId: model.id,
      },
    });
    modelIds.push(model.id);

    const release = await prisma.commercialDataRelease.create({
      data: {
        activatedAt: new Date('2026-07-24T05:30:00.000Z'),
        activatedByRef: 'commercial-release-owner',
        approvalEvidenceRef: 'evidence://commercial/release',
        approvedAt: new Date('2026-07-24T05:20:00.000Z'),
        approvedByRef: 'commercial-release-reviewer',
        effectiveAt: new Date('2026-07-24T00:00:00.000Z'),
        market: 'VN',
        releaseVersion: `commercial-${randomUUID()}`,
        revision: 2,
        sourceRevisionId: source.id,
        state: CommercialReleaseState.ACTIVE,
        submittedByRef: 'commercial-release-operator',
      },
    });
    releaseIds.push(release.id);

    const offer = await prisma.priceOffer.create({
      data: {
        amountMinor: 900_000_000n,
        channel: CommercialChannel.PUBLIC,
        commercialReleaseId: release.id,
        currency: 'VND',
        eligibilityRules: {},
        eligibilitySchemaVersion: 'test-v1',
        market: 'VN',
        offerCode: 'PUBLIC-MSRP',
        priceType: PriceType.MSRP,
        sourceRevisionId: source.id,
        taxTreatment: TaxTreatment.TAX_INCLUSIVE,
        validFrom: new Date('2026-07-24T00:00:00.000Z'),
        validTo: new Date('2026-07-25T00:00:00.000Z'),
        vehicleVariantId: variant.id,
      },
    });
    await prisma.promotion.create({
      data: {
        benefitDefinition: { gift: 'synthetic' },
        benefitSchemaVersion: 'test-v1',
        benefitType: PromotionBenefitType.IN_KIND,
        channel: CommercialChannel.PUBLIC,
        commercialReleaseId: release.id,
        eligibilityRules: {},
        eligibilitySchemaVersion: 'test-v1',
        market: 'VN',
        promotionCode: 'PUBLIC-GIFT',
        promotionVersion: 'v1',
        sourceRevisionId: source.id,
        stackingPolicy: PromotionStackingPolicy.EXCLUSIVE,
        title: 'Integration test promotion',
        validFrom: new Date('2026-07-24T00:00:00.000Z'),
        validTo: new Date('2026-07-25T00:00:00.000Z'),
        vehicleModelId: model.id,
      },
    });
    return {
      modelId: model.id,
      offerId: offer.id,
      releaseId: release.id,
      sourceRevisionId: source.id,
      variantId: variant.id,
    };
  }

  it('returns one active fresh release and fails closed on a blocking anomaly', async () => {
    const fixture = await createFixture();
    const now = new Date('2026-07-24T06:00:00.000Z');

    await expect(
      repository.getActiveForModel(fixture.modelId, 'VN', now),
    ).resolves.toMatchObject({
      market: 'VN',
      priceOffers: [{ amountMinor: '900000000', priceType: 'msrp' }],
      promotions: [{ promotionCode: 'PUBLIC-GIFT' }],
    });

    await prisma.commercialFactAnomaly.create({
      data: {
        disposition: CommercialAnomalyDisposition.OPEN,
        evidence: { observed: 'unexpected price' },
        priceOfferId: fixture.offerId,
        ruleCode: 'PRICE_BUSINESS_CONFLICT',
        ruleVersion: 'test-v1',
        severity: CommercialAnomalySeverity.BLOCKING,
      },
    });

    await expect(
      repository.getActiveForModel(fixture.modelId, 'VN', now),
    ).resolves.toBeNull();
  });

  it('enforces positive price amounts in PostgreSQL', async () => {
    const fixture = await createFixture();
    const original = await prisma.priceOffer.findUniqueOrThrow({
      where: { id: fixture.offerId },
    });

    await expect(
      prisma.priceOffer.create({
        data: {
          amountMinor: 0n,
          channel: original.channel,
          commercialReleaseId: original.commercialReleaseId,
          currency: original.currency,
          eligibilityRules: {},
          eligibilitySchemaVersion: original.eligibilitySchemaVersion,
          id: randomUUID(),
          market: original.market,
          offerCode: 'INVALID-ZERO',
          priceType: original.priceType,
          sourceRevisionId: original.sourceRevisionId,
          taxTreatment: original.taxTreatment,
          validFrom: original.validFrom,
          validTo: original.validTo,
          vehicleVariantId: original.vehicleVariantId,
        },
      }),
    ).rejects.toThrow();
  });

  it('approves, atomically activates and rolls back commercial releases', async () => {
    const fixture = await createFixture();
    const now = new Date('2026-07-24T06:00:00.000Z');
    const draft = await prisma.commercialDataRelease.create({
      data: {
        effectiveAt: new Date('2026-07-24T00:00:00.000Z'),
        market: 'VN',
        releaseVersion: `draft-${randomUUID()}`,
        sourceRevisionId: fixture.sourceRevisionId,
        submittedByRef: 'commercial-release-operator',
      },
    });
    releaseIds.push(draft.id);
    await prisma.priceOffer.create({
      data: {
        amountMinor: 950_000_000n,
        channel: CommercialChannel.PUBLIC,
        commercialReleaseId: draft.id,
        currency: 'VND',
        eligibilityRules: {},
        eligibilitySchemaVersion: 'test-v1',
        market: 'VN',
        offerCode: 'PUBLIC-MSRP-NEXT',
        priceType: PriceType.MSRP,
        sourceRevisionId: fixture.sourceRevisionId,
        taxTreatment: TaxTreatment.TAX_INCLUSIVE,
        validFrom: new Date('2026-07-24T00:00:00.000Z'),
        validTo: new Date('2026-07-25T00:00:00.000Z'),
        vehicleVariantId: fixture.variantId,
      },
    });

    await expect(
      workflow.approve({
        correlationId: randomUUID(),
        evidenceRef: 'evidence://commercial/release-review',
        expectedRevision: 0,
        now,
        releaseId: draft.id,
        reviewerRef: 'commercial-release-reviewer',
      }),
    ).resolves.toMatchObject({ revision: 1, state: 'approved' });
    await expect(
      workflow.activate({
        actorRef: 'commercial-release-operator',
        correlationId: randomUUID(),
        expectedRevision: 1,
        now,
        releaseId: draft.id,
      }),
    ).resolves.toMatchObject({ revision: 2, state: 'active' });
    expect(
      await prisma.commercialDataRelease.count({
        where: { market: 'VN', state: CommercialReleaseState.ACTIVE },
      }),
    ).toBe(1);

    await expect(
      workflow.rollback({
        actorRef: 'commercial-release-operator',
        correlationId: randomUUID(),
        expectedCurrentRevision: 2,
        expectedTargetRevision: 3,
        now,
        targetReleaseId: fixture.releaseId,
      }),
    ).resolves.toMatchObject({ revision: 4, state: 'active' });
  });
});
