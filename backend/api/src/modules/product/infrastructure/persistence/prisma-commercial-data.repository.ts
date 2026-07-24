import { Injectable } from '@nestjs/common';
import {
  CommercialChannel,
  CommercialReleaseState,
  type DataClassification,
  PriceType,
  SourceApprovalState,
} from '../../../../generated/prisma/enums';
import { PrismaService } from '../../../../platform/database/prisma.service';
import {
  assertSourceRevisionEligible,
  SourceRevisionNotEligibleError,
  type SourceRevisionEvidence,
} from '../../../../platform/provenance/source-revision-policy';
import { CommercialDataRepository } from '../../application/ports/commercial-data.repository';
import {
  assertNoBlockingCommercialAnomaly,
  assertPriceOfferPublishable,
  CommercialFactUnavailableError,
  type CommercialSourceView,
  VN_PUBLIC_VEHICLE_PRICE_POLICY,
  type VehicleCommercialView,
} from '../../domain/commercial-facts';

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

type SourceRecord = Omit<
  SourceRevisionEvidence,
  'approvalState' | 'classification'
> & {
  readonly approvalState: SourceApprovalState;
  readonly classification: DataClassification;
  readonly revision: string;
  readonly source: string;
};

function sourceEvidence<T extends SourceRecord>(
  source: T,
): SourceRevisionEvidence {
  return {
    ...source,
    approvalState: source.approvalState.toLowerCase() as
      'approved' | 'pending' | 'rejected' | 'retired',
    classification: source.classification.toLowerCase() as
      'public' | 'internal' | 'confidential' | 'restricted',
  };
}

function sourceView(source: SourceRecord): CommercialSourceView {
  return {
    effectiveFrom: source.effectiveAt,
    expiresAt: source.expiresAt,
    freshness: 'fresh',
    observedAt: source.observedAt,
    revision: source.revision,
    sourceId: source.source,
  };
}

@Injectable()
export class PrismaCommercialDataRepository extends CommercialDataRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async getActiveForModel(
    modelId: string,
    market: string,
    now: Date,
  ): Promise<VehicleCommercialView | null> {
    const release = await this.prisma.commercialDataRelease.findFirst({
      orderBy: { activatedAt: 'desc' },
      select: {
        id: true,
        market: true,
        priceOffers: {
          orderBy: [{ vehicleVariantId: 'asc' }, { offerCode: 'asc' }],
          select: {
            amountMinor: true,
            anomalies: {
              select: {
                disposition: true,
                ruleCode: true,
                severity: true,
              },
            },
            channel: true,
            currency: true,
            market: true,
            offerCode: true,
            priceType: true,
            sourceRevision: {
              select: {
                revision: true,
                source: true,
                ...sourceEvidenceSelection,
              },
            },
            taxTreatment: true,
            validFrom: true,
            validTo: true,
            vehicleVariantId: true,
          },
          where: {
            channel: CommercialChannel.PUBLIC,
            priceType: { in: [PriceType.MSRP, PriceType.LIST] },
            validFrom: { lte: now },
            OR: [{ validTo: null }, { validTo: { gt: now } }],
            vehicleVariant: { vehicleModelId: modelId },
          },
        },
        promotions: {
          orderBy: [{ promotionCode: 'asc' }, { promotionVersion: 'asc' }],
          select: {
            anomalies: {
              select: {
                disposition: true,
                ruleCode: true,
                severity: true,
              },
            },
            benefitAmountMinor: true,
            benefitPercentage: true,
            benefitType: true,
            channel: true,
            currency: true,
            promotionCode: true,
            promotionVersion: true,
            sourceRevision: {
              select: {
                revision: true,
                source: true,
                ...sourceEvidenceSelection,
              },
            },
            stackingPolicy: true,
            title: true,
            validFrom: true,
            validTo: true,
            vehicleModelId: true,
            vehicleVariantId: true,
          },
          where: {
            channel: CommercialChannel.PUBLIC,
            validFrom: { lte: now },
            OR: [
              { vehicleModelId: null, vehicleVariantId: null },
              { vehicleModelId: modelId },
              { vehicleVariant: { vehicleModelId: modelId } },
            ],
            AND: [{ OR: [{ validTo: null }, { validTo: { gt: now } }] }],
          },
        },
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
        effectiveAt: { lte: now },
        market,
        sourceRevision: {
          approvalState: SourceApprovalState.APPROVED,
          effectiveAt: { lte: now },
          OR: [{ expiresAt: null }, { expiresAt: { gt: now } }],
          retiredAt: null,
        },
        state: CommercialReleaseState.ACTIVE,
      },
    });
    if (release === null) return null;

    try {
      assertSourceRevisionEligible(
        sourceEvidence(release.sourceRevision),
        'vehicle-commercial-data',
        now,
      );
      for (const offer of release.priceOffers) {
        if (offer.market !== release.market) {
          throw new CommercialFactUnavailableError(
            'offer and release markets differ',
          );
        }
        assertPriceOfferPublishable(
          {
            amountMinor: offer.amountMinor,
            channel: offer.channel.toLowerCase() as
              'public' | 'retail' | 'fleet' | 'employee',
            currency: offer.currency,
            market: offer.market,
            priceType: offer.priceType.toLowerCase() as
              'msrp' | 'list' | 'option' | 'service',
            source: sourceEvidence(offer.sourceRevision),
            validFrom: offer.validFrom,
            validTo: offer.validTo,
          },
          offer.anomalies.map((anomaly) => ({
            disposition: anomaly.disposition.toLowerCase() as
              'open' | 'accepted' | 'rejected' | 'resolved',
            ruleCode: anomaly.ruleCode,
            severity: anomaly.severity.toLowerCase() as 'warning' | 'blocking',
          })),
          VN_PUBLIC_VEHICLE_PRICE_POLICY,
          now,
        );
      }
      for (const promotion of release.promotions) {
        assertSourceRevisionEligible(
          sourceEvidence(promotion.sourceRevision),
          'vehicle-commercial-data',
          now,
        );
        assertNoBlockingCommercialAnomaly(
          promotion.anomalies.map((anomaly) => ({
            disposition: anomaly.disposition.toLowerCase() as
              'open' | 'accepted' | 'rejected' | 'resolved',
            ruleCode: anomaly.ruleCode,
            severity: anomaly.severity.toLowerCase() as 'warning' | 'blocking',
          })),
        );
      }
    } catch (error) {
      if (
        error instanceof SourceRevisionNotEligibleError ||
        error instanceof CommercialFactUnavailableError
      ) {
        return null;
      }
      throw error;
    }

    return {
      market: release.market,
      priceOffers: release.priceOffers.map((offer) => ({
        amountMinor: offer.amountMinor.toString(),
        channel: offer.channel.toLowerCase() as
          'public' | 'retail' | 'fleet' | 'employee',
        currency: offer.currency,
        market: offer.market,
        offerCode: offer.offerCode,
        priceType: offer.priceType.toLowerCase() as
          'msrp' | 'list' | 'option' | 'service',
        source: sourceView(offer.sourceRevision),
        taxTreatment: offer.taxTreatment.toLowerCase() as
          'tax_inclusive' | 'tax_exclusive' | 'not_applicable',
        validFrom: offer.validFrom,
        validTo: offer.validTo,
        variantId: offer.vehicleVariantId,
      })),
      promotions: release.promotions.map((promotion) => ({
        benefitAmountMinor: promotion.benefitAmountMinor?.toString() ?? null,
        benefitPercentage: promotion.benefitPercentage?.toNumber() ?? null,
        benefitType: promotion.benefitType.toLowerCase() as
          'fixed_amount' | 'percentage' | 'in_kind' | 'composite',
        channel: promotion.channel.toLowerCase() as
          'public' | 'retail' | 'fleet' | 'employee',
        currency: promotion.currency,
        promotionCode: promotion.promotionCode,
        promotionVersion: promotion.promotionVersion,
        source: sourceView(promotion.sourceRevision),
        stackingPolicy: promotion.stackingPolicy.toLowerCase() as
          'exclusive' | 'stackable' | 'rule_based',
        title: promotion.title,
        validFrom: promotion.validFrom,
        validTo: promotion.validTo,
        vehicleModelId: promotion.vehicleModelId,
        vehicleVariantId: promotion.vehicleVariantId,
      })),
      releaseVersion: release.releaseVersion,
    };
  }
}
