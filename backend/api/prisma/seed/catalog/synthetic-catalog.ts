export const SYNTHETIC_CATALOG_RELEASE_ID =
  '00000000-0000-4000-a000-000000000101';
export const SYNTHETIC_SOURCE_REVISION_ID =
  '00000000-0000-4000-a000-000000000102';
export const SYNTHETIC_COMMERCIAL_RELEASE_ID =
  '00000000-0000-4000-a000-000000000106';
export const SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID =
  '00000000-0000-4000-a000-000000000107';

export const syntheticCatalog = {
  market: 'VN',
  model: {
    brandCode: 'VFBIZ_SYNTHETIC',
    canonicalName: 'Synthetic City EV',
    category: 'synthetic-passenger-vehicle',
    id: '00000000-0000-4000-a000-000000000103',
    modelCode: 'SYNTHETIC_CITY_EV',
    modelYear: 2026,
    slug: 'synthetic-city-ev',
  },
  release: {
    effectiveAt: '2026-01-01T00:00:00.000Z',
    id: SYNTHETIC_CATALOG_RELEASE_ID,
    releaseVersion: 'local-synthetic-v1',
  },
  source: {
    id: SYNTHETIC_SOURCE_REVISION_ID,
    revision: 'local-synthetic-v1',
    source: 'vfbiz-local-synthetic-fixture',
  },
  variants: [
    {
      canonicalName: 'Synthetic City EV Standard',
      connectorStandards: ['CCS2'],
      declaredRangeKm: 300,
      drivetrain: 'FWD',
      grossBatteryCapacityKwh: 45,
      id: '00000000-0000-4000-a000-000000000104',
      maximumAcChargePowerKw: 7.4,
      maximumDcChargePowerKw: 80,
      rangeTestStandard: 'SYNTHETIC',
      seats: 5,
      usableBatteryCapacityKwh: 42,
      variantCode: 'SYNTHETIC_STANDARD',
    },
    {
      canonicalName: 'Synthetic City EV Plus',
      connectorStandards: ['CCS2'],
      declaredRangeKm: 400,
      drivetrain: 'AWD',
      grossBatteryCapacityKwh: 62,
      id: '00000000-0000-4000-a000-000000000105',
      maximumAcChargePowerKw: 11,
      maximumDcChargePowerKw: 120,
      rangeTestStandard: 'SYNTHETIC',
      seats: 5,
      usableBatteryCapacityKwh: 58,
      variantCode: 'SYNTHETIC_PLUS',
    },
  ],
} as const;

export const syntheticCommercialData = {
  market: 'VN',
  priceOffers: [
    {
      amountMinor: 750_000_000n,
      id: '00000000-0000-4000-a000-000000000301',
      offerCode: 'SYNTHETIC-STANDARD-MSRP',
      variantId: syntheticCatalog.variants[0].id,
    },
    {
      amountMinor: 950_000_000n,
      id: '00000000-0000-4000-a000-000000000302',
      offerCode: 'SYNTHETIC-PLUS-MSRP',
      variantId: syntheticCatalog.variants[1].id,
    },
  ],
  promotion: {
    amountMinor: 50_000_000n,
    code: 'SYNTHETIC-JULY-OFFER',
    id: '00000000-0000-4000-a000-000000000303',
    title: 'Synthetic local development offer',
    version: 'v1',
  },
  release: {
    effectiveAt: '2026-01-01T00:00:00.000Z',
    id: SYNTHETIC_COMMERCIAL_RELEASE_ID,
    releaseVersion: 'local-synthetic-commercial-v1',
  },
  source: {
    id: SYNTHETIC_COMMERCIAL_SOURCE_REVISION_ID,
    revision: 'local-synthetic-commercial-v1',
    source: 'vfbiz-local-synthetic-commercial-fixture',
  },
} as const;
