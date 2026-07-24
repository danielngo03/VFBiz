import { Injectable } from '@nestjs/common';
import { PrismaService } from '../../../../platform/database/prisma.service';
import {
  SourceApprovalState,
  VehicleCatalogReleaseState,
} from '../../../../generated/prisma/enums';
import { SourceRevisionNotEligibleError } from '../../../../platform/provenance/source-revision-policy';
import { VehicleCatalogRepository } from '../../application/ports/vehicle-catalog.repository';
import {
  assertCatalogFactProvenance,
  assertPublishableCatalogSource,
  CatalogProvenanceError,
  requiredVariantFactGroups,
} from '../../domain/catalog-publication-policy';
import type {
  CatalogFreshness,
  VehicleModelCatalogView,
  VehicleVariantCatalogView,
} from '../../domain/vehicle-catalog';

function decimalNumber(value: { toNumber(): number } | null): number | null {
  return value?.toNumber() ?? null;
}

const sourceEvidenceSelection = {
  approvalEvidenceRef: true,
  approvalState: true,
  approvedAt: true,
  approvedByRef: true,
  checksum: true,
  classification: true,
  effectiveAt: true,
  expiresAt: true,
  freshnessTtlSeconds: true,
  ingestedAt: true,
  licenseId: true,
  observedAt: true,
  ownerRef: true,
  permittedPurposes: true,
  provenanceUri: true,
  retiredAt: true,
  submittedByRef: true,
} as const;

@Injectable()
export class PrismaVehicleCatalogRepository extends VehicleCatalogRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async listActive(
    market: string,
    now: Date,
  ): Promise<readonly VehicleModelCatalogView[] | null> {
    const release = await this.prisma.vehicleCatalogRelease.findFirst({
      orderBy: { activatedAt: 'desc' },
      select: {
        id: true,
        factProvenance: {
          select: {
            factGroup: true,
            sourceRevision: { select: sourceEvidenceSelection },
            subjectRef: true,
            subjectType: true,
          },
        },
        market: true,
        releaseVersion: true,
        sourceRevision: {
          select: {
            revision: true,
            source: true,
            ...sourceEvidenceSelection,
          },
        },
      },
      where: {
        activatedAt: { lte: now, not: null },
        effectiveAt: { lte: now },
        market,
        sourceRevision: {
          approvalState: SourceApprovalState.APPROVED,
          approvedAt: { not: null },
          effectiveAt: { lte: now },
          OR: [{ expiresAt: null }, { expiresAt: { gt: now } }],
          retiredAt: null,
        },
        state: VehicleCatalogReleaseState.ACTIVE,
      },
    });
    if (release === null) return null;

    try {
      assertPublishableCatalogSource(release.sourceRevision, now);
    } catch (error) {
      if (error instanceof SourceRevisionNotEligibleError) return null;
      throw error;
    }
    const freshness: CatalogFreshness = 'fresh';

    const revisions = await this.prisma.vehicleModelRevision.findMany({
      orderBy: [{ canonicalName: 'asc' }, { vehicleModelId: 'asc' }],
      select: {
        canonicalName: true,
        category: true,
        commercialStatus: true,
        modelYear: true,
        vehicleModel: {
          select: {
            brandCode: true,
            id: true,
            modelCode: true,
            slug: true,
            variants: {
              orderBy: { variantCode: 'asc' },
              select: {
                id: true,
                variantCode: true,
                variantRevisions: {
                  select: {
                    canonicalName: true,
                    commercialStatus: true,
                    connectorStandards: true,
                    declaredRangeKm: true,
                    drivetrain: true,
                    grossBatteryCapacityKwh: true,
                    maximumAcChargePowerKw: true,
                    maximumDcChargePowerKw: true,
                    rangeTestStandard: true,
                    seats: true,
                    usableBatteryCapacityKwh: true,
                  },
                  take: 1,
                  where: { catalogReleaseId: release.id },
                },
              },
            },
          },
        },
      },
      where: { catalogReleaseId: release.id },
    });

    const modelIds = new Set(
      revisions.map((revision) => revision.vehicleModel.id),
    );
    const variants = revisions.flatMap((revision) =>
      revision.vehicleModel.variants.flatMap((variant) => {
        const current = variant.variantRevisions[0];
        if (current === undefined) return [];
        return [
          {
            id: variant.id,
            requiredGroups: requiredVariantFactGroups(current),
          },
        ];
      }),
    );
    try {
      assertCatalogFactProvenance(
        release.id,
        modelIds,
        variants,
        release.factProvenance,
        now,
      );
    } catch (error) {
      if (
        error instanceof CatalogProvenanceError ||
        error instanceof SourceRevisionNotEligibleError
      ) {
        return null;
      }
      throw error;
    }

    return revisions.map((revision) => ({
      brandCode: revision.vehicleModel.brandCode,
      category: revision.category,
      commercialStatus: revision.commercialStatus.toLowerCase() as
        'announced' | 'active' | 'discontinued',
      id: revision.vehicleModel.id,
      market: release.market,
      modelCode: revision.vehicleModel.modelCode,
      modelYear: revision.modelYear,
      name: revision.canonicalName,
      releaseVersion: release.releaseVersion,
      slug: revision.vehicleModel.slug,
      source: {
        effectiveFrom: release.sourceRevision.effectiveAt,
        freshness,
        revision: release.sourceRevision.revision,
        sourceId: release.sourceRevision.source,
      },
      variants: revision.vehicleModel.variants.flatMap((variant) => {
        const current = variant.variantRevisions[0];
        if (current === undefined) return [];
        const view: VehicleVariantCatalogView = {
          commercialStatus: current.commercialStatus.toLowerCase() as
            'announced' | 'active' | 'discontinued',
          connectorStandards: current.connectorStandards,
          declaredRangeKm: decimalNumber(current.declaredRangeKm),
          drivetrain: current.drivetrain,
          grossBatteryCapacityKwh: decimalNumber(
            current.grossBatteryCapacityKwh,
          ),
          id: variant.id,
          maximumAcChargePowerKw: decimalNumber(current.maximumAcChargePowerKw),
          maximumDcChargePowerKw: decimalNumber(current.maximumDcChargePowerKw),
          name: current.canonicalName,
          rangeTestStandard: current.rangeTestStandard,
          seats: current.seats,
          usableBatteryCapacityKwh: decimalNumber(
            current.usableBatteryCapacityKwh,
          ),
          variantCode: variant.variantCode,
        };
        return [view];
      }),
    }));
  }

  async isVariantSelectable(
    variantId: string,
    market: string,
    now: Date,
  ): Promise<boolean> {
    const catalog = await this.listActive(market, now);
    return (
      catalog?.some((model) =>
        model.variants.some(
          (variant) =>
            variant.id === variantId &&
            (variant.commercialStatus === 'active' ||
              variant.commercialStatus === 'announced'),
        ),
      ) ?? false
    );
  }
}
