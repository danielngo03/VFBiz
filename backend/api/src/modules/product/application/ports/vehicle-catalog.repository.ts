import type { VehicleModelCatalogView } from '../../domain/vehicle-catalog';

export abstract class VehicleCatalogRepository {
  abstract listActive(
    market: string,
    now: Date,
  ): Promise<readonly VehicleModelCatalogView[] | null>;

  abstract isVariantSelectable(
    variantId: string,
    market: string,
    now: Date,
  ): Promise<boolean>;
}
