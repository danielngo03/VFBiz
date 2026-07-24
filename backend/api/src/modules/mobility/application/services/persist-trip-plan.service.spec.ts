import { TripPlanRepository } from '../ports/trip-plan.repository';
import { PersistTripPlanService } from './persist-trip-plan.service';
import {
  TripPlanPersistenceMapper,
  type PersistedTripPlanRecord,
} from './trip-plan-persistence-mapper';

class StubTripPlanRepository extends TripPlanRepository {
  saved: PersistedTripPlanRecord | null = null;

  deleteExpired(): Promise<number> {
    return Promise.resolve(0);
  }

  save(record: PersistedTripPlanRecord): Promise<void> {
    this.saved = record;
    return Promise.resolve();
  }
}

describe('PersistTripPlanService', () => {
  const request = {
    departureSocPct: 82,
    destination: { placeId: 'ChIJ-destination' },
    origin: { placeId: 'ChIJ-origin' },
    preference: 'balanced' as const,
    reserveSocPct: 15,
    vehicleProfileId: 'vf8-eco-2026',
    waypoints: [],
  };
  const result = {
    chargingStops: [],
    confidence: null,
    currency: null,
    status: 'feasible',
    totalChargingSeconds: 0,
    totalCostMinor: 0,
    totalDistanceMeters: 100000,
    totalDurationSeconds: 5400,
    warnings: [],
  };

  it('saves only mapped request/result data and forces providerPayloadStored=false', async () => {
    const repository = new StubTripPlanRepository();
    const service = new PersistTripPlanService(
      repository,
      new TripPlanPersistenceMapper(
        'test-only-pseudonymization-key-with-32-bytes',
      ),
    );

    await service.execute({
      algorithmRevision: 'energy-v1',
      cachePolicy: 'derived-15m',
      calculatedAt: new Date('2026-07-22T12:00:00.000Z'),
      customerProfileId: null,
      expiresAt: new Date('2026-07-22T12:15:00.000Z'),
      id: '9bcf8d28-e037-46a5-9827-40481f2c1447',
      request,
      result,
      retentionUntil: new Date('2026-07-23T12:00:00.000Z'),
      routeProvider: 'google-routes',
      sourceRevisions: ['energy:v1', 'stations:v4', 'tariff:v3'],
      vehicleEnergyProfileId: 'a3274b23-9f9e-4538-843d-df04a137af1d',
    });

    expect(repository.saved).toMatchObject({
      providerPayloadStored: false,
      requestSchema: 'trip-request-v1',
      resultSchema: 'trip-result-v1',
      status: 'feasible',
    });
    expect(JSON.stringify(repository.saved)).not.toContain('ChIJ-origin');
    expect(JSON.stringify(repository.saved)).not.toContain('ChIJ-destination');
  });

  it('rejects raw provider fields before calling the repository', async () => {
    const repository = new StubTripPlanRepository();
    const service = new PersistTripPlanService(
      repository,
      new TripPlanPersistenceMapper(
        'test-only-pseudonymization-key-with-32-bytes',
      ),
    );

    await expect(
      service.execute({
        algorithmRevision: 'energy-v1',
        cachePolicy: 'derived-15m',
        calculatedAt: new Date('2026-07-22T12:00:00.000Z'),
        customerProfileId: null,
        expiresAt: new Date('2026-07-22T12:15:00.000Z'),
        id: '9bcf8d28-e037-46a5-9827-40481f2c1447',
        request,
        result: { ...result, polyline: 'raw-provider-data' },
        retentionUntil: new Date('2026-07-23T12:00:00.000Z'),
        routeProvider: 'google-routes',
        sourceRevisions: ['energy:v1'],
        vehicleEnergyProfileId: 'a3274b23-9f9e-4538-843d-df04a137af1d',
      }),
    ).rejects.toThrow('Unapproved trip result field');
    expect(repository.saved).toBeNull();
  });
});
