export type CatalogFreshness = 'fresh' | 'stale' | 'unavailable';

export interface CatalogSourceView {
  readonly effectiveFrom: Date;
  readonly freshness: CatalogFreshness;
  readonly revision: string;
  readonly sourceId: string;
}

export interface VehicleVariantCatalogView {
  readonly commercialStatus: 'announced' | 'active' | 'discontinued';
  readonly connectorStandards: readonly string[];
  readonly declaredRangeKm: number | null;
  readonly drivetrain: string | null;
  readonly grossBatteryCapacityKwh: number | null;
  readonly id: string;
  readonly maximumAcChargePowerKw: number | null;
  readonly maximumDcChargePowerKw: number | null;
  readonly name: string;
  readonly rangeTestStandard: string | null;
  readonly seats: number | null;
  readonly usableBatteryCapacityKwh: number | null;
  readonly variantCode: string;
}

export interface VehicleModelCatalogView {
  readonly brandCode: string;
  readonly category: string;
  readonly commercialStatus: 'announced' | 'active' | 'discontinued';
  readonly id: string;
  readonly market: string;
  readonly modelCode: string;
  readonly modelYear: number | null;
  readonly name: string;
  readonly releaseVersion: string;
  readonly slug: string;
  readonly source: CatalogSourceView;
  readonly variants: readonly VehicleVariantCatalogView[];
}

export class VehicleCatalogUnavailableError extends Error {
  constructor() {
    super('An approved fresh vehicle catalog is unavailable.');
    this.name = 'VehicleCatalogUnavailableError';
  }
}
