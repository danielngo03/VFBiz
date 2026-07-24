import 'dotenv/config';
import { createHash } from 'node:crypto';
import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from '../../src/generated/prisma/client';
import {
  CommercialChannel,
  CommercialReleaseState,
  DataClassification,
  PriceType,
  PromotionBenefitType,
  PromotionStackingPolicy,
  SourceApprovalState,
  TaxTreatment,
  VehicleCatalogReleaseState,
  VehicleCommercialStatus,
  VehicleFactGroup,
  VehicleFactSubjectType,
} from '../../src/generated/prisma/enums';
import { validateOfficialProductSourceCandidates } from './catalog/official-source-candidates';
import {
  syntheticCommercialData,
  syntheticCatalog,
  SYNTHETIC_COMMERCIAL_RELEASE_ID,
  SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID,
  SYNTHETIC_CATALOG_RELEASE_ID,
  SYNTHETIC_SOURCE_REVISION_ID,
} from './catalog/synthetic-catalog';

type SeedMode = 'validate' | 'synthetic';

function seedMode(): SeedMode {
  const argument = process.argv.find((value) => value.startsWith('--mode='));
  const mode = argument?.slice('--mode='.length) ?? 'validate';
  if (mode !== 'validate' && mode !== 'synthetic') {
    throw new Error(`Unsupported seed mode: ${mode}`);
  }
  return mode;
}

function assertLocalSyntheticSeed(databaseUrl: string): void {
  if (process.env.NODE_ENV === 'production') {
    throw new Error('Synthetic seed is forbidden in production.');
  }
  if (process.env.VFBIZ_ALLOW_SYNTHETIC_SEED !== 'true') {
    throw new Error(
      'Set VFBIZ_ALLOW_SYNTHETIC_SEED=true to acknowledge local synthetic data.',
    );
  }

  const url = new URL(databaseUrl);
  if (!['127.0.0.1', 'localhost', '::1'].includes(url.hostname)) {
    throw new Error(
      'Synthetic seed may only target a loopback PostgreSQL host.',
    );
  }
  if (url.pathname !== '/vfbiz') {
    throw new Error('Synthetic seed may only target the local vfbiz database.');
  }
}

function fixtureChecksum(): string {
  return createHash('sha256')
    .update(JSON.stringify(syntheticCatalog))
    .digest('hex');
}

function commercialFixtureChecksum(): string {
  return createHash('sha256')
    .update(
      JSON.stringify(syntheticCommercialData, (_key, value: unknown) =>
        typeof value === 'bigint' ? value.toString() : value,
      ),
    )
    .digest('hex');
}

async function seedSyntheticCatalog(prisma: PrismaClient): Promise<void> {
  const activeRelease = await prisma.vehicleCatalogRelease.findFirst({
    select: { id: true, releaseVersion: true },
    where: {
      market: syntheticCatalog.market,
      state: VehicleCatalogReleaseState.ACTIVE,
    },
  });
  if (
    activeRelease !== null &&
    activeRelease.id !== SYNTHETIC_CATALOG_RELEASE_ID
  ) {
    throw new Error(
      `Refusing to supersede active release ${activeRelease.releaseVersion}.`,
    );
  }

  const checksum = fixtureChecksum();
  const existingSource = await prisma.sourceRevision.findUnique({
    select: { checksum: true },
    where: { id: SYNTHETIC_SOURCE_REVISION_ID },
  });
  if (existingSource !== null && existingSource.checksum !== checksum) {
    throw new Error(
      'Synthetic fixture changed without a new source revision and release version.',
    );
  }

  const effectiveAt = new Date(syntheticCatalog.release.effectiveAt);
  const expiresAt = new Date('2036-01-01T00:00:00.000Z');
  const approvedAt = new Date('2026-01-01T00:00:02.000Z');
  const observedAt = new Date('2026-01-01T00:00:00.000Z');
  const ingestedAt = new Date('2026-01-01T00:00:01.000Z');

  await prisma.$transaction(async (transaction) => {
    await transaction.sourceRevision.upsert({
      create: {
        approvalEvidenceRef: 'urn:vfbiz:synthetic:approval:local-v1',
        approvalState: SourceApprovalState.APPROVED,
        approvedAt,
        approvedByRef: 'local-fixture-reviewer',
        checksum,
        classification: DataClassification.PUBLIC,
        effectiveAt,
        expiresAt,
        freshnessTtlSeconds: 315_360_000,
        id: syntheticCatalog.source.id,
        ingestedAt,
        licenseId: 'VFBIZ-SYNTHETIC-LOCAL-ONLY',
        observedAt,
        ownerRef: 'api-test-data-owner',
        permittedPurposes: ['vehicle-catalog'],
        provenanceUri: 'urn:vfbiz:synthetic:vehicle-catalog:local-v1',
        revision: syntheticCatalog.source.revision,
        source: syntheticCatalog.source.source,
        submittedByRef: 'local-fixture-builder',
      },
      update: {},
      where: { id: syntheticCatalog.source.id },
    });

    await transaction.vehicleModel.upsert({
      create: {
        brandCode: syntheticCatalog.model.brandCode,
        id: syntheticCatalog.model.id,
        modelCode: syntheticCatalog.model.modelCode,
        slug: syntheticCatalog.model.slug,
      },
      update: {},
      where: { id: syntheticCatalog.model.id },
    });

    for (const variant of syntheticCatalog.variants) {
      await transaction.vehicleVariant.upsert({
        create: {
          id: variant.id,
          variantCode: variant.variantCode,
          vehicleModelId: syntheticCatalog.model.id,
        },
        update: {},
        where: { id: variant.id },
      });
    }

    await transaction.vehicleCatalogRelease.upsert({
      create: {
        activatedAt: approvedAt,
        activatedByRef: 'local-fixture-activator',
        approvalEvidenceRef: 'urn:vfbiz:synthetic:approval:local-v1',
        approvedAt,
        approvedByRef: 'local-fixture-reviewer',
        effectiveAt,
        id: syntheticCatalog.release.id,
        market: syntheticCatalog.market,
        releaseVersion: syntheticCatalog.release.releaseVersion,
        sourceRevisionId: syntheticCatalog.source.id,
        state: VehicleCatalogReleaseState.ACTIVE,
        submittedByRef: 'local-fixture-builder',
      },
      update: {
        activatedAt: approvedAt,
        activatedByRef: 'local-fixture-activator',
        approvalEvidenceRef: 'urn:vfbiz:synthetic:approval:local-v1',
        approvedAt,
        approvedByRef: 'local-fixture-reviewer',
        state: VehicleCatalogReleaseState.ACTIVE,
      },
      where: { id: syntheticCatalog.release.id },
    });

    await transaction.vehicleModelRevision.upsert({
      create: {
        canonicalName: syntheticCatalog.model.canonicalName,
        catalogReleaseId: syntheticCatalog.release.id,
        category: syntheticCatalog.model.category,
        commercialStatus: VehicleCommercialStatus.ACTIVE,
        id: '00000000-0000-4000-a000-000000000201',
        modelYear: syntheticCatalog.model.modelYear,
        vehicleModelId: syntheticCatalog.model.id,
      },
      update: {},
      where: {
        vehicleModelId_catalogReleaseId: {
          catalogReleaseId: syntheticCatalog.release.id,
          vehicleModelId: syntheticCatalog.model.id,
        },
      },
    });

    for (const [index, variant] of syntheticCatalog.variants.entries()) {
      await transaction.vehicleVariantRevision.upsert({
        create: {
          canonicalName: variant.canonicalName,
          catalogReleaseId: syntheticCatalog.release.id,
          commercialStatus: VehicleCommercialStatus.ACTIVE,
          connectorStandards: [...variant.connectorStandards],
          declaredRangeKm: variant.declaredRangeKm,
          drivetrain: variant.drivetrain,
          extensionData: { syntheticFixture: true },
          grossBatteryCapacityKwh: variant.grossBatteryCapacityKwh,
          id: `00000000-0000-4000-a000-00000000020${index + 2}`,
          maximumAcChargePowerKw: variant.maximumAcChargePowerKw,
          maximumDcChargePowerKw: variant.maximumDcChargePowerKw,
          rangeTestStandard: variant.rangeTestStandard,
          seats: variant.seats,
          specificationSchemaVersion: 'synthetic-v1',
          usableBatteryCapacityKwh: variant.usableBatteryCapacityKwh,
          vehicleVariantId: variant.id,
        },
        update: {},
        where: {
          vehicleVariantId_catalogReleaseId: {
            catalogReleaseId: syntheticCatalog.release.id,
            vehicleVariantId: variant.id,
          },
        },
      });
    }

    const provenance = [
      {
        factGroup: VehicleFactGroup.IDENTITY_COMMERCIAL,
        subjectRef: syntheticCatalog.release.id,
        subjectType: VehicleFactSubjectType.RELEASE,
      },
      {
        factGroup: VehicleFactGroup.IDENTITY_COMMERCIAL,
        subjectRef: syntheticCatalog.model.id,
        subjectType: VehicleFactSubjectType.MODEL,
      },
      ...syntheticCatalog.variants.flatMap((variant) =>
        [
          VehicleFactGroup.IDENTITY_COMMERCIAL,
          VehicleFactGroup.TECHNICAL_HOMOLOGATION,
          VehicleFactGroup.BATTERY_RANGE_CHARGING,
          VehicleFactGroup.OPTIONS_COMPATIBILITY,
        ].map((factGroup) => ({
          factGroup,
          subjectRef: variant.id,
          subjectType: VehicleFactSubjectType.VARIANT,
        })),
      ),
    ];

    for (const binding of provenance) {
      await transaction.vehicleFactProvenanceBinding.upsert({
        create: {
          catalogReleaseId: syntheticCatalog.release.id,
          factGroup: binding.factGroup,
          sourceRevisionId: syntheticCatalog.source.id,
          subjectRef: binding.subjectRef,
          subjectType: binding.subjectType,
        },
        update: {},
        where: {
          catalogReleaseId_subjectType_subjectRef_factGroup: {
            catalogReleaseId: syntheticCatalog.release.id,
            factGroup: binding.factGroup,
            subjectRef: binding.subjectRef,
            subjectType: binding.subjectType,
          },
        },
      });
    }

    const commercialChecksum = commercialFixtureChecksum();
    const existingCommercialSource =
      await transaction.sourceRevision.findUnique({
        select: { checksum: true },
        where: { id: SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID },
      });
    if (
      existingCommercialSource !== null &&
      existingCommercialSource.checksum !== commercialChecksum
    ) {
      throw new Error(
        'Synthetic commercial fixture changed without a new source and release version.',
      );
    }

    await transaction.sourceRevision.upsert({
      create: {
        approvalEvidenceRef: 'urn:vfbiz:synthetic:approval:local-commercial-v1',
        approvalState: SourceApprovalState.APPROVED,
        approvedAt,
        approvedByRef: 'local-fixture-reviewer',
        checksum: commercialChecksum,
        classification: DataClassification.PUBLIC,
        effectiveAt,
        expiresAt,
        freshnessTtlSeconds: 315_360_000,
        id: SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID,
        ingestedAt,
        licenseId: 'VFBIZ-SYNTHETIC-LOCAL-ONLY',
        observedAt,
        ownerRef: 'api-test-data-owner',
        permittedPurposes: ['vehicle-commercial-data'],
        provenanceUri: 'urn:vfbiz:synthetic:vehicle-commercial-data:local-v1',
        revision: syntheticCommercialData.source.revision,
        source: syntheticCommercialData.source.source,
        submittedByRef: 'local-fixture-builder',
      },
      update: {},
      where: { id: SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID },
    });

    await transaction.commercialDataRelease.upsert({
      create: {
        activatedAt: approvedAt,
        activatedByRef: 'local-fixture-activator',
        approvalEvidenceRef: 'urn:vfbiz:synthetic:approval:local-commercial-v1',
        approvedAt,
        approvedByRef: 'local-fixture-reviewer',
        effectiveAt,
        id: SYNTHETIC_COMMERCIAL_RELEASE_ID,
        market: syntheticCommercialData.market,
        releaseVersion: syntheticCommercialData.release.releaseVersion,
        sourceRevisionId: SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID,
        state: CommercialReleaseState.ACTIVE,
        submittedByRef: 'local-fixture-builder',
      },
      update: {
        activatedAt: approvedAt,
        activatedByRef: 'local-fixture-activator',
        approvalEvidenceRef: 'urn:vfbiz:synthetic:approval:local-commercial-v1',
        approvedAt,
        approvedByRef: 'local-fixture-reviewer',
        state: CommercialReleaseState.ACTIVE,
      },
      where: { id: SYNTHETIC_COMMERCIAL_RELEASE_ID },
    });

    for (const offer of syntheticCommercialData.priceOffers) {
      await transaction.priceOffer.upsert({
        create: {
          amountMinor: offer.amountMinor,
          channel: CommercialChannel.PUBLIC,
          commercialReleaseId: SYNTHETIC_COMMERCIAL_RELEASE_ID,
          currency: 'VND',
          eligibilityRules: { syntheticOnly: true },
          eligibilitySchemaVersion: 'synthetic-v1',
          id: offer.id,
          market: syntheticCommercialData.market,
          offerCode: offer.offerCode,
          priceType: PriceType.MSRP,
          sourceRevisionId: SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID,
          taxTreatment: TaxTreatment.TAX_INCLUSIVE,
          validFrom: effectiveAt,
          validTo: expiresAt,
          vehicleVariantId: offer.variantId,
        },
        update: {},
        where: { id: offer.id },
      });
    }

    await transaction.promotion.upsert({
      create: {
        benefitAmountMinor: syntheticCommercialData.promotion.amountMinor,
        benefitDefinition: { syntheticOnly: true },
        benefitSchemaVersion: 'synthetic-v1',
        benefitType: PromotionBenefitType.FIXED_AMOUNT,
        channel: CommercialChannel.PUBLIC,
        commercialReleaseId: SYNTHETIC_COMMERCIAL_RELEASE_ID,
        currency: 'VND',
        eligibilityRules: { syntheticOnly: true },
        eligibilitySchemaVersion: 'synthetic-v1',
        id: syntheticCommercialData.promotion.id,
        market: syntheticCommercialData.market,
        promotionCode: syntheticCommercialData.promotion.code,
        promotionVersion: syntheticCommercialData.promotion.version,
        sourceRevisionId: SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID,
        stackingPolicy: PromotionStackingPolicy.EXCLUSIVE,
        title: syntheticCommercialData.promotion.title,
        validFrom: effectiveAt,
        validTo: expiresAt,
        vehicleModelId: syntheticCatalog.model.id,
      },
      update: {},
      where: { id: syntheticCommercialData.promotion.id },
    });
  });
}

async function main(): Promise<void> {
  validateOfficialProductSourceCandidates();
  if (seedMode() === 'validate') {
    process.stdout.write(
      'Product source candidates are valid; no database data was written.\n',
    );
    return;
  }

  const databaseUrl = process.env.VFBIZ_DATABASE_URL;
  if (databaseUrl === undefined) {
    throw new Error('VFBIZ_DATABASE_URL is required.');
  }
  assertLocalSyntheticSeed(databaseUrl);

  const prisma = new PrismaClient({
    adapter: new PrismaPg(databaseUrl),
  });
  try {
    await prisma.$connect();
    await seedSyntheticCatalog(prisma);
    process.stdout.write(
      `Seeded ${syntheticCatalog.release.releaseVersion} into local PostgreSQL.\n`,
    );
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
