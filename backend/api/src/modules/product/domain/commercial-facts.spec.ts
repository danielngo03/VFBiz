import {
  assertNoBlockingCommercialAnomaly,
  assertPriceOfferPublishable,
  CommercialFactUnavailableError,
} from './commercial-facts';

const now = new Date('2026-07-24T00:00:00.000Z');
const source = {
  approvalEvidenceRef: 'urn:vfbiz:approval:commercial',
  approvalState: 'approved' as const,
  approvedAt: new Date('2026-07-22T00:00:00.000Z'),
  approvedByRef: 'reviewer',
  checksum: 'a'.repeat(64),
  classification: 'public' as const,
  effectiveAt: new Date('2026-07-22T00:00:00.000Z'),
  expiresAt: new Date('2026-08-22T00:00:00.000Z'),
  freshnessTtlSeconds: 2_592_000,
  ingestedAt: new Date('2026-07-22T00:00:00.000Z'),
  licenseId: 'APPROVED-COMMERCIAL',
  observedAt: new Date('2026-07-22T00:00:00.000Z'),
  ownerRef: 'commercial-data-owner',
  permittedPurposes: ['vehicle-commercial-data'],
  provenanceUri: 'urn:vfbiz:source:commercial',
  retiredAt: null,
  submittedByRef: 'submitter',
};
const policy = {
  maximumAmountMinor: 10_000_000_000n,
  minimumAmountMinor: 100_000_000n,
  ruleVersion: 'vn-public-vehicle-price-v1',
};

describe('commercial fact publication policy', () => {
  it('accepts a current sourced price inside the approved anomaly range', () => {
    expect(() =>
      assertPriceOfferPublishable(
        {
          amountMinor: 900_000_000n,
          channel: 'public',
          currency: 'VND',
          market: 'VN',
          priceType: 'msrp',
          source,
          validFrom: new Date('2026-07-23T00:00:00.000Z'),
          validTo: null,
        },
        [],
        policy,
        now,
      ),
    ).not.toThrow();
  });

  it('fails closed when a vehicle price is outside the governed range', () => {
    expect(() =>
      assertPriceOfferPublishable(
        {
          amountMinor: 109_000n,
          channel: 'public',
          currency: 'VND',
          market: 'VN',
          priceType: 'msrp',
          source,
          validFrom: new Date('2026-07-23T00:00:00.000Z'),
          validTo: null,
        },
        [],
        policy,
        now,
      ),
    ).toThrow(CommercialFactUnavailableError);
  });

  it('blocks unresolved and explicitly accepted blocking anomalies', () => {
    expect(() =>
      assertNoBlockingCommercialAnomaly([
        {
          disposition: 'accepted',
          ruleCode: 'PRICE_BUSINESS_CONFLICT',
          severity: 'blocking',
        },
      ]),
    ).toThrow('blocking anomaly PRICE_BUSINESS_CONFLICT');
  });

  it('allows a rejected false positive without hiding the fact', () => {
    expect(() =>
      assertNoBlockingCommercialAnomaly([
        {
          disposition: 'rejected',
          ruleCode: 'PRICE_OUTLIER',
          severity: 'blocking',
        },
      ]),
    ).not.toThrow();
  });
});
