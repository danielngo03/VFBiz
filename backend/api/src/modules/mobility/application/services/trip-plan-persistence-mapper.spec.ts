import { TripPlanPersistenceMapper } from './trip-plan-persistence-mapper';

describe('TripPlanPersistenceMapper', () => {
  const mapper = new TripPlanPersistenceMapper(
    'test-only-pseudonymization-key-with-32-bytes',
  );

  it('pseudonymizes provider place identifiers before persistence', () => {
    const stored = mapper.toStoredRequest({
      departureSocPct: 82,
      destination: { placeId: 'ChIJ-destination' },
      origin: { placeId: 'ChIJ-origin' },
      preference: 'balanced',
      reserveSocPct: 15,
      vehicleProfileId: 'vf8-eco-2026',
      waypoints: [{ placeId: 'ChIJ-waypoint' }],
    });
    const serialized = JSON.stringify(stored);

    expect(serialized).not.toContain('ChIJ-origin');
    expect(serialized).not.toContain('ChIJ-destination');
    expect(serialized).not.toContain('ChIJ-waypoint');
    expect(stored).toMatchObject({
      departureSocPct: 82,
      preference: 'balanced',
      reserveSocPct: 15,
      schema: 'trip-request-v1',
      vehicleProfileId: 'vf8-eco-2026',
    });
    expect(stored.originRefHash).toMatch(/^[a-f0-9]{64}$/);
    expect(stored.destinationRefHash).toMatch(/^[a-f0-9]{64}$/);
    expect(stored.waypointRefHashes).toHaveLength(1);
  });

  it('persists only the approved deterministic result shape', () => {
    expect(
      mapper.toStoredResult({
        chargingStops: [
          {
            arrivalSocPct: 12,
            chargingSeconds: 1320,
            costMinor: 185000,
            stationId: 'station-42',
            targetSocPct: 68,
          },
        ],
        confidence: {
          expectedEnergyKwh: 48.2,
          maximumEnergyKwh: 54.1,
          minimumEnergyKwh: 43.6,
        },
        currency: 'VND',
        status: 'feasible',
        totalChargingSeconds: 1320,
        totalCostMinor: 185000,
        totalDistanceMeters: 286000,
        totalDurationSeconds: 15120,
        warnings: [],
      }),
    ).toEqual(
      expect.objectContaining({
        schema: 'trip-result-v1',
        status: 'feasible',
        totalDistanceMeters: 286000,
      }),
    );
  });

  it.each(['polyline', 'providerPayload', 'geocodedWaypoints', 'rawResponse'])(
    'rejects the raw provider field %s',
    (field) => {
      expect(() =>
        mapper.toStoredResult({
          chargingStops: [],
          confidence: null,
          currency: null,
          status: 'unavailable',
          totalChargingSeconds: null,
          totalCostMinor: null,
          totalDistanceMeters: null,
          totalDurationSeconds: null,
          warnings: ['route-provider-unavailable'],
          [field]: { secret: 'must-not-be-stored' },
        }),
      ).toThrow('Unapproved trip result field');
    },
  );
});
