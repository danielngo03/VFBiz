import { createHmac } from 'node:crypto';
import { Injectable } from '@nestjs/common';

type TripPreference = 'balanced' | 'fastest' | 'lowest_cost';
type TripStatus = 'feasible' | 'no_feasible_route' | 'unavailable';

export interface TripPlaceInput {
  readonly placeId: string;
}

export interface TripPlanPersistenceRequest {
  readonly departureSocPct: number;
  readonly destination: TripPlaceInput;
  readonly origin: TripPlaceInput;
  readonly preference?: TripPreference;
  readonly reserveSocPct: number;
  readonly vehicleProfileId: string;
  readonly waypoints?: readonly TripPlaceInput[];
}

export interface StoredTripPlanRequest {
  readonly departureSocPct: number;
  readonly destinationRefHash: string;
  readonly originRefHash: string;
  readonly preference: TripPreference;
  readonly reserveSocPct: number;
  readonly schema: 'trip-request-v1';
  readonly vehicleProfileId: string;
  readonly waypointRefHashes: readonly string[];
}

export interface StoredChargingStop {
  readonly arrivalSocPct: number;
  readonly chargingSeconds: number;
  readonly costMinor: number;
  readonly stationId: string;
  readonly targetSocPct: number;
}

export interface StoredTripConfidence {
  readonly expectedEnergyKwh: number;
  readonly maximumEnergyKwh: number;
  readonly minimumEnergyKwh: number;
}

export interface StoredTripPlanResult {
  readonly chargingStops: readonly StoredChargingStop[];
  readonly confidence: StoredTripConfidence | null;
  readonly currency: string | null;
  readonly schema: 'trip-result-v1';
  readonly status: TripStatus;
  readonly totalChargingSeconds: number | null;
  readonly totalCostMinor: number | null;
  readonly totalDistanceMeters: number | null;
  readonly totalDurationSeconds: number | null;
  readonly warnings: readonly string[];
}

export interface PersistedTripPlanRecord {
  readonly algorithmRevision: string;
  readonly cachePolicy: string;
  readonly calculatedAt: Date;
  readonly customerProfileId: string | null;
  readonly expiresAt: Date;
  readonly failureCode: string | null;
  readonly id: string;
  readonly privacyClassification: 'customer-confidential';
  readonly providerPayloadStored: false;
  readonly request: StoredTripPlanRequest;
  readonly requestFingerprint: string;
  readonly requestSchema: 'trip-request-v1';
  readonly result: StoredTripPlanResult;
  readonly resultSchema: 'trip-result-v1';
  readonly retentionUntil: Date;
  readonly routeProvider: string;
  readonly routeRequestHash: string;
  readonly sourceRevisions: readonly string[];
  readonly status: TripStatus;
  readonly vehicleEnergyProfileId: string;
  readonly warnings: readonly string[];
}

const ROOT_RESULT_FIELDS = new Set([
  'chargingStops',
  'confidence',
  'currency',
  'status',
  'totalChargingSeconds',
  'totalCostMinor',
  'totalDistanceMeters',
  'totalDurationSeconds',
  'warnings',
]);
const CHARGING_STOP_FIELDS = new Set([
  'arrivalSocPct',
  'chargingSeconds',
  'costMinor',
  'stationId',
  'targetSocPct',
]);
const CONFIDENCE_FIELDS = new Set([
  'expectedEnergyKwh',
  'maximumEnergyKwh',
  'minimumEnergyKwh',
]);

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  return value as Record<string, unknown>;
}

function assertAllowedFields(
  value: Record<string, unknown>,
  allowed: ReadonlySet<string>,
): void {
  for (const field of Object.keys(value)) {
    if (!allowed.has(field)) {
      throw new Error(`Unapproved trip result field: ${field}`);
    }
  }
}

function requireFiniteNumber(
  value: unknown,
  field: string,
  nullable = false,
): number | null {
  if (nullable && value === null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new Error(`${field} must be a non-negative finite number.`);
  }
  return value;
}

function requireString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`${field} must be a non-empty string.`);
  }
  return value;
}

@Injectable()
export class TripPlanPersistenceMapper {
  constructor(private readonly pseudonymizationKey: string) {
    if (Buffer.byteLength(pseudonymizationKey, 'utf8') < 32) {
      throw new Error(
        'Trip pseudonymization key must contain at least 32 bytes.',
      );
    }
  }

  toStoredRequest(request: TripPlanPersistenceRequest): StoredTripPlanRequest {
    return {
      departureSocPct: request.departureSocPct,
      destinationRefHash: this.pseudonymize(request.destination.placeId),
      originRefHash: this.pseudonymize(request.origin.placeId),
      preference: request.preference ?? 'balanced',
      reserveSocPct: request.reserveSocPct,
      schema: 'trip-request-v1',
      vehicleProfileId: request.vehicleProfileId,
      waypointRefHashes: (request.waypoints ?? []).map(({ placeId }) =>
        this.pseudonymize(placeId),
      ),
    };
  }

  toStoredResult(input: unknown): StoredTripPlanResult {
    const value = requireRecord(input, 'Trip result');
    assertAllowedFields(value, ROOT_RESULT_FIELDS);

    if (!Array.isArray(value.chargingStops)) {
      throw new Error('chargingStops must be an array.');
    }
    const chargingStops = value.chargingStops.map((item) => {
      const stop = requireRecord(item, 'Charging stop');
      assertAllowedFields(stop, CHARGING_STOP_FIELDS);
      return {
        arrivalSocPct: requireFiniteNumber(
          stop.arrivalSocPct,
          'arrivalSocPct',
        ) as number,
        chargingSeconds: requireFiniteNumber(
          stop.chargingSeconds,
          'chargingSeconds',
        ) as number,
        costMinor: requireFiniteNumber(stop.costMinor, 'costMinor') as number,
        stationId: requireString(stop.stationId, 'stationId'),
        targetSocPct: requireFiniteNumber(
          stop.targetSocPct,
          'targetSocPct',
        ) as number,
      };
    });

    let confidence: StoredTripConfidence | null = null;
    if (value.confidence !== null) {
      const candidate = requireRecord(value.confidence, 'Trip confidence');
      assertAllowedFields(candidate, CONFIDENCE_FIELDS);
      confidence = {
        expectedEnergyKwh: requireFiniteNumber(
          candidate.expectedEnergyKwh,
          'expectedEnergyKwh',
        ) as number,
        maximumEnergyKwh: requireFiniteNumber(
          candidate.maximumEnergyKwh,
          'maximumEnergyKwh',
        ) as number,
        minimumEnergyKwh: requireFiniteNumber(
          candidate.minimumEnergyKwh,
          'minimumEnergyKwh',
        ) as number,
      };
    }

    const statuses: readonly TripStatus[] = [
      'feasible',
      'no_feasible_route',
      'unavailable',
    ];
    if (!statuses.includes(value.status as TripStatus)) {
      throw new Error('status is not an approved trip status.');
    }
    const currency = value.currency;
    if (
      currency !== null &&
      (typeof currency !== 'string' || !/^[A-Z]{3}$/.test(currency))
    ) {
      throw new Error('currency must be an ISO 4217 code or null.');
    }
    const warningsInput: unknown = value.warnings;
    if (
      !Array.isArray(warningsInput) ||
      (warningsInput as unknown[]).some(
        (warning) => typeof warning !== 'string',
      )
    ) {
      throw new Error('warnings must be an array of strings.');
    }
    const warnings = (warningsInput as unknown[]).map((warning) => {
      if (typeof warning !== 'string') {
        throw new Error('warnings must be an array of strings.');
      }
      return warning;
    });

    return {
      chargingStops,
      confidence,
      currency,
      schema: 'trip-result-v1',
      status: value.status as TripStatus,
      totalChargingSeconds: requireFiniteNumber(
        value.totalChargingSeconds,
        'totalChargingSeconds',
        true,
      ),
      totalCostMinor: requireFiniteNumber(
        value.totalCostMinor,
        'totalCostMinor',
        true,
      ),
      totalDistanceMeters: requireFiniteNumber(
        value.totalDistanceMeters,
        'totalDistanceMeters',
        true,
      ),
      totalDurationSeconds: requireFiniteNumber(
        value.totalDurationSeconds,
        'totalDurationSeconds',
        true,
      ),
      warnings,
    };
  }

  private pseudonymize(value: string): string {
    return createHmac('sha256', this.pseudonymizationKey)
      .update(value, 'utf8')
      .digest('hex');
  }
}
