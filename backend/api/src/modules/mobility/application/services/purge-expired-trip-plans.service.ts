import { Injectable } from '@nestjs/common';
import { TripPlanRepository } from '../ports/trip-plan.repository';

export interface PurgeExpiredTripPlansInput {
  readonly batchSize: number;
  readonly before: Date;
  readonly maximumBatches?: number;
}

export interface PurgeExpiredTripPlansResult {
  readonly batches: number;
  readonly deleted: number;
}

@Injectable()
export class PurgeExpiredTripPlansService {
  constructor(private readonly repository: TripPlanRepository) {}

  async execute(
    input: PurgeExpiredTripPlansInput,
  ): Promise<PurgeExpiredTripPlansResult> {
    if (!Number.isSafeInteger(input.batchSize) || input.batchSize <= 0) {
      throw new Error('Trip purge batch size must be a positive integer.');
    }
    const maximumBatches = input.maximumBatches ?? 100;
    if (!Number.isSafeInteger(maximumBatches) || maximumBatches <= 0) {
      throw new Error('Trip purge batch ceiling must be a positive integer.');
    }

    let batches = 0;
    let deleted = 0;
    while (batches < maximumBatches) {
      const count = await this.repository.deleteExpired({
        before: input.before,
        limit: input.batchSize,
      });
      batches += 1;
      deleted += count;
      if (count < input.batchSize) break;
    }
    return { batches, deleted };
  }
}
