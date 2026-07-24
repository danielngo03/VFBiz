import { createHash } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import { TripPlanRepository } from '../ports/trip-plan.repository';
import {
  TripPlanPersistenceMapper,
  type TripPlanPersistenceRequest,
} from './trip-plan-persistence-mapper';

export interface PersistTripPlanInput {
  readonly algorithmRevision: string;
  readonly cachePolicy: string;
  readonly calculatedAt: Date;
  readonly customerProfileId: string | null;
  readonly expiresAt: Date;
  readonly failureCode?: string | null;
  readonly id: string;
  readonly request: TripPlanPersistenceRequest;
  readonly result: unknown;
  readonly retentionUntil: Date;
  readonly routeProvider: string;
  readonly sourceRevisions: readonly string[];
  readonly vehicleEnergyProfileId: string;
}

function checksum(value: unknown): string {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex');
}

@Injectable()
export class PersistTripPlanService {
  constructor(
    private readonly repository: TripPlanRepository,
    private readonly mapper: TripPlanPersistenceMapper,
  ) {}

  async execute(input: PersistTripPlanInput): Promise<void> {
    if (input.retentionUntil.getTime() <= input.calculatedAt.getTime()) {
      throw new Error('Trip retention must end after calculation time.');
    }
    if (input.expiresAt.getTime() > input.retentionUntil.getTime()) {
      throw new Error('Trip cache expiry cannot exceed retention.');
    }
    const request = this.mapper.toStoredRequest(input.request);
    const result = this.mapper.toStoredResult(input.result);
    await this.repository.save({
      algorithmRevision: input.algorithmRevision,
      cachePolicy: input.cachePolicy,
      calculatedAt: input.calculatedAt,
      customerProfileId: input.customerProfileId,
      expiresAt: input.expiresAt,
      failureCode: input.failureCode ?? null,
      id: input.id,
      privacyClassification: 'customer-confidential',
      providerPayloadStored: false,
      request,
      requestFingerprint: checksum(request),
      requestSchema: 'trip-request-v1',
      result,
      resultSchema: 'trip-result-v1',
      retentionUntil: input.retentionUntil,
      routeProvider: input.routeProvider,
      routeRequestHash: checksum({
        destinationRefHash: request.destinationRefHash,
        originRefHash: request.originRefHash,
        waypointRefHashes: request.waypointRefHashes,
      }),
      sourceRevisions: [...input.sourceRevisions],
      status: result.status,
      vehicleEnergyProfileId: input.vehicleEnergyProfileId,
      warnings: result.warnings,
    });
  }
}
