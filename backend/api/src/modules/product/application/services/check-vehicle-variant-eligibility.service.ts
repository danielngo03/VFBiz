import { Injectable } from '@nestjs/common';
import { VehicleCatalogRepository } from '../ports/vehicle-catalog.repository';

@Injectable()
export class CheckVehicleVariantEligibilityService {
  constructor(private readonly repository: VehicleCatalogRepository) {}

  isSelectable(
    variantId: string,
    market: string,
    now = new Date(),
  ): Promise<boolean> {
    return this.repository.isVariantSelectable(
      variantId,
      market.toUpperCase(),
      now,
    );
  }
}
