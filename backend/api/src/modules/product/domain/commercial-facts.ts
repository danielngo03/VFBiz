import {
  assertSourceRevisionEligible,
  type SourceRevisionEvidence,
} from '../../../platform/provenance/source-revision-policy';

export type CommercialFactFreshness = 'fresh';

export interface CommercialAnomalyView {
  readonly disposition: 'open' | 'accepted' | 'rejected' | 'resolved';
  readonly ruleCode: string;
  readonly severity: 'warning' | 'blocking';
}

export interface PriceOfferCandidate {
  readonly amountMinor: bigint;
  readonly channel: 'public' | 'retail' | 'fleet' | 'employee';
  readonly currency: string;
  readonly market: string;
  readonly priceType: 'msrp' | 'list' | 'option' | 'service';
  readonly source: SourceRevisionEvidence;
  readonly validFrom: Date;
  readonly validTo: Date | null;
}

export interface PriceAnomalyPolicy {
  readonly maximumAmountMinor: bigint;
  readonly minimumAmountMinor: bigint;
  readonly ruleVersion: string;
}

export const VN_PUBLIC_VEHICLE_PRICE_POLICY: PriceAnomalyPolicy = Object.freeze(
  {
    maximumAmountMinor: 10_000_000_000n,
    minimumAmountMinor: 100_000_000n,
    ruleVersion: 'vn-public-vehicle-price-v1',
  },
);

export interface CommercialSourceView {
  readonly effectiveFrom: Date;
  readonly expiresAt: Date | null;
  readonly freshness: CommercialFactFreshness;
  readonly observedAt: Date;
  readonly revision: string;
  readonly sourceId: string;
}

export interface PriceOfferView {
  readonly amountMinor: string;
  readonly channel: 'public' | 'retail' | 'fleet' | 'employee';
  readonly currency: string;
  readonly market: string;
  readonly offerCode: string;
  readonly priceType: 'msrp' | 'list' | 'option' | 'service';
  readonly source: CommercialSourceView;
  readonly taxTreatment: 'tax_inclusive' | 'tax_exclusive' | 'not_applicable';
  readonly validFrom: Date;
  readonly validTo: Date | null;
  readonly variantId: string;
}

export interface PromotionView {
  readonly benefitAmountMinor: string | null;
  readonly benefitPercentage: number | null;
  readonly benefitType: 'fixed_amount' | 'percentage' | 'in_kind' | 'composite';
  readonly channel: 'public' | 'retail' | 'fleet' | 'employee';
  readonly currency: string | null;
  readonly promotionCode: string;
  readonly promotionVersion: string;
  readonly source: CommercialSourceView;
  readonly stackingPolicy: 'exclusive' | 'stackable' | 'rule_based';
  readonly title: string;
  readonly validFrom: Date;
  readonly validTo: Date | null;
  readonly vehicleModelId: string | null;
  readonly vehicleVariantId: string | null;
}

export interface VehicleCommercialView {
  readonly market: string;
  readonly priceOffers: readonly PriceOfferView[];
  readonly promotions: readonly PromotionView[];
  readonly releaseVersion: string;
}

export class CommercialFactUnavailableError extends Error {
  constructor(readonly reason: string) {
    super(`Commercial fact is unavailable: ${reason}.`);
    this.name = 'CommercialFactUnavailableError';
  }
}

export function assertNoBlockingCommercialAnomaly(
  anomalies: readonly CommercialAnomalyView[],
): void {
  const blocking = anomalies.find(
    (anomaly) =>
      anomaly.severity === 'blocking' &&
      (anomaly.disposition === 'open' || anomaly.disposition === 'accepted'),
  );
  if (blocking !== undefined) {
    throw new CommercialFactUnavailableError(
      `blocking anomaly ${blocking.ruleCode}`,
    );
  }
}

export function assertPriceOfferPublishable(
  offer: PriceOfferCandidate,
  anomalies: readonly CommercialAnomalyView[],
  policy: PriceAnomalyPolicy,
  now: Date,
): void {
  assertSourceRevisionEligible(offer.source, 'vehicle-commercial-data', now);
  if (
    !/^[A-Z]{2,8}$/.test(offer.market) ||
    !/^[A-Z]{3}$/.test(offer.currency)
  ) {
    throw new CommercialFactUnavailableError('invalid market or currency');
  }
  if (
    offer.validFrom.getTime() > now.getTime() ||
    (offer.validTo !== null && offer.validTo.getTime() <= now.getTime())
  ) {
    throw new CommercialFactUnavailableError('offer is outside validity');
  }
  if (
    offer.amountMinor < policy.minimumAmountMinor ||
    offer.amountMinor > policy.maximumAmountMinor
  ) {
    throw new CommercialFactUnavailableError(
      `amount failed anomaly policy ${policy.ruleVersion}`,
    );
  }
  assertNoBlockingCommercialAnomaly(anomalies);
}
