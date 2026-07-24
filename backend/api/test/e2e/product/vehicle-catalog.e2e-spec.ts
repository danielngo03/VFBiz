import { Test } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { AppModule } from '../../../src/app.module';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import { VehicleCatalogRepository } from '../../../src/modules/product/application/ports/vehicle-catalog.repository';
import { CommercialDataRepository } from '../../../src/modules/product/application/ports/commercial-data.repository';

const repository = {
  listActive: jest.fn().mockResolvedValue([
    {
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
    },
  ]),
};
const commercialRepository = {
  getActiveForModel: jest.fn().mockResolvedValue({
    market: 'VN',
    priceOffers: [
      {
        amountMinor: '900000000',
        channel: 'public',
        currency: 'VND',
        market: 'VN',
        offerCode: 'VF8-MSRP-PUBLIC',
        priceType: 'msrp',
        source: {
          effectiveFrom: new Date('2026-07-23T00:00:00.000Z'),
          expiresAt: new Date('2026-08-01T00:00:00.000Z'),
          freshness: 'fresh',
          observedAt: new Date('2026-07-23T00:00:00.000Z'),
          revision: 'commercial-r1',
          sourceId: 'erp-commercial',
        },
        taxTreatment: 'tax_inclusive',
        validFrom: new Date('2026-07-23T00:00:00.000Z'),
        validTo: null,
        variantId: '3d8e924f-d746-4677-8f61-f71fa3df849e',
      },
    ],
    promotions: [],
    releaseVersion: 'commercial-2026-07-23',
  }),
};

describe('Vehicle Catalog public boundary (e2e)', () => {
  let app: NestFastifyApplication;

  beforeAll(async () => {
    const moduleFixture = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(VehicleCatalogRepository)
      .useValue(repository)
      .overrideProvider(CommercialDataRepository)
      .useValue(commercialRepository)
      .compile();
    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );
    await configureApplication(app);
    await app.init();
    await app.getHttpAdapter().getInstance().ready();
  });

  it('returns the active release without authentication', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/vehicles/models?market=VN',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject([
      {
        market: 'VN',
        modelCode: 'VF_8',
        releaseVersion: 'catalog-2026-07-23',
        source: { freshness: 'fresh', revision: 'source-r1' },
      },
    ]);
  });

  it('rejects unsupported market instead of silently substituting data', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/vehicles/models?market=US',
    });

    expect(response.statusCode).toBe(400);
    expect(response.json()).toMatchObject({ code: 'UNSUPPORTED_MARKET' });
  });

  it('returns governed commercial facts separately from the catalog', async () => {
    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/vehicles/models/vf-8/commercial?market=VN',
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({
      market: 'VN',
      priceOffers: [
        {
          amountMinor: '900000000',
          currency: 'VND',
          priceType: 'msrp',
          source: { freshness: 'fresh', revision: 'commercial-r1' },
        },
      ],
      releaseVersion: 'commercial-2026-07-23',
    });
  });

  afterAll(async () => app.close());
});
