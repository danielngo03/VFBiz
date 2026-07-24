import { VehicleCatalogRepository } from '../ports/vehicle-catalog.repository';
import type { VehicleModelCatalogView } from '../../domain/vehicle-catalog';
import { VehicleCatalogUnavailableError } from '../../domain/vehicle-catalog';
import { ReadVehicleCatalogService } from './read-vehicle-catalog.service';

const model: VehicleModelCatalogView = {
  brandCode: 'VINFAST',
  category: 'suv',
  commercialStatus: 'active',
  id: 'a762adbb-8d2c-4c22-aa86-c6fe83cc7431',
  market: 'VN',
  modelCode: 'VF_8',
  modelYear: 2026,
  name: 'VF 8',
  releaseVersion: 'catalog-2026-07-23',
  slug: 'vf-8',
  source: {
    effectiveFrom: new Date('2026-07-23T00:00:00.000Z'),
    freshness: 'fresh',
    revision: 'source-r1',
    sourceId: 'pim',
  },
  variants: [],
};

class StubVehicleCatalogRepository extends VehicleCatalogRepository {
  constructor(
    private readonly result: readonly VehicleModelCatalogView[] | null,
  ) {
    super();
  }

  listActive(): Promise<readonly VehicleModelCatalogView[] | null> {
    return Promise.resolve(this.result);
  }

  isVariantSelectable(): Promise<boolean> {
    return Promise.resolve(false);
  }
}

describe('ReadVehicleCatalogService', () => {
  it('returns one atomic active catalog release', async () => {
    const service = new ReadVehicleCatalogService(
      new StubVehicleCatalogRepository([model]),
    );

    await expect(
      service.list('VN', new Date('2026-07-23T01:00:00.000Z')),
    ).resolves.toEqual([model]);
  });

  it('fails closed when no approved fresh release exists', async () => {
    const service = new ReadVehicleCatalogService(
      new StubVehicleCatalogRepository(null),
    );

    await expect(service.list('VN')).rejects.toBeInstanceOf(
      VehicleCatalogUnavailableError,
    );
  });

  it('does not search across another release when resolving a slug', async () => {
    const service = new ReadVehicleCatalogService(
      new StubVehicleCatalogRepository([model]),
    );

    await expect(service.getBySlug('VN', 'vf-9')).resolves.toBeNull();
  });
});
