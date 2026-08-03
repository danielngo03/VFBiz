import { ResolveVehicleCatalogIdentityService } from './resolve-vehicle-catalog-identity.service';

const now = new Date('2026-07-29T08:00:00.000Z');
const vf8 = {
  brandCode: 'VINFAST',
  category: 'suv',
  commercialStatus: 'active' as const,
  id: 'vehicle-model-vf8',
  market: 'VN',
  modelCode: 'VF8',
  modelYear: 2026,
  name: 'VF 8',
  releaseVersion: 'catalog-release-v1',
  slug: 'vf-8',
  source: {
    effectiveFrom: new Date('2026-07-01T00:00:00.000Z'),
    freshness: 'fresh' as const,
    revision: 'source-r1',
    sourceId: 'vinfast-catalog',
  },
  variants: [],
};

describe('ResolveVehicleCatalogIdentityService', () => {
  it.each(['VF 8', 'vf8', 'vf-8'])(
    'resolves an exact normalized model label: %s',
    async (candidate) => {
      const repository = {
        isVariantSelectable: jest.fn(),
        listActive: jest.fn().mockResolvedValue([vf8]),
      };
      const service = new ResolveVehicleCatalogIdentityService(repository);

      await expect(
        service.resolveModel({ candidate, market: 'VN', now }),
      ).resolves.toEqual({
        kind: 'resolved',
        value: {
          modelId: vf8.id,
          modelReference: vf8.slug,
          releaseRevision: vf8.releaseVersion,
          sourceRevision: vf8.source.revision,
        },
      });
    },
  );

  it('fails closed when the active catalog is unavailable or ambiguous', async () => {
    const repository = {
      isVariantSelectable: jest.fn(),
      listActive: jest
        .fn()
        .mockResolvedValueOnce(null)
        .mockResolvedValueOnce([vf8, { ...vf8, id: 'duplicate' }]),
    };
    const service = new ResolveVehicleCatalogIdentityService(repository);

    await expect(
      service.resolveModel({ candidate: 'VF 8', market: 'VN', now }),
    ).resolves.toEqual({ kind: 'unavailable' });
    await expect(
      service.resolveModel({ candidate: 'VF 8', market: 'VN', now }),
    ).resolves.toEqual({ kind: 'not_found' });
  });
});
