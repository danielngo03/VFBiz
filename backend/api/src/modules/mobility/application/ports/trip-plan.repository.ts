import type { PersistedTripPlanRecord } from '../services/trip-plan-persistence-mapper';

export abstract class TripPlanRepository {
  abstract deleteExpired(input: {
    readonly before: Date;
    readonly limit: number;
  }): Promise<number>;

  abstract save(record: PersistedTripPlanRecord): Promise<void>;
}
