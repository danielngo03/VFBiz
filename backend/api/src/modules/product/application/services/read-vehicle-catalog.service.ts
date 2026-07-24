import { Injectable } from '@nestjs/common';
import { VehicleCatalogRepository } from '../ports/vehicle-catalog.repository';
import {
  VehicleCatalogUnavailableError,
  type VehicleModelCatalogView,
} from '../../domain/vehicle-catalog';

@Injectable()
export class ReadVehicleCatalogService {
  constructor(private readonly repository: VehicleCatalogRepository) {}

  async list(
    market: string,
    now = new Date(),
  ): Promise<readonly VehicleModelCatalogView[]> {
    const models = await this.repository.listActive(market, now);
    if (models === null) throw new VehicleCatalogUnavailableError();
    return models;
  }

  async getBySlug(
    market: string,
    slug: string,
    now = new Date(),
  ): Promise<VehicleModelCatalogView | null> {
    const models = await this.list(market, now);
    return models.find((model) => model.slug === slug) ?? null;
  }
}
