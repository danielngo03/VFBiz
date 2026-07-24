import { PurgeExpiredTripPlansService } from './purge-expired-trip-plans.service';
import type { TripPlanRepository } from '../ports/trip-plan.repository';
import type { PersistedTripPlanRecord } from './trip-plan-persistence-mapper';

class StubTripPlanRepository implements TripPlanRepository {
  readonly calls: Array<{ before: Date; limit: number }> = [];

  constructor(private readonly deletionCounts: number[]) {}

  save(record: PersistedTripPlanRecord): Promise<void> {
    void record;
    return Promise.resolve();
  }

  deleteExpired(input: { before: Date; limit: number }): Promise<number> {
    this.calls.push(input);
    return Promise.resolve(this.deletionCounts.shift() ?? 0);
  }
}

describe('PurgeExpiredTripPlansService', () => {
  it('purges bounded batches until the repository returns a partial batch', async () => {
    const repository = new StubTripPlanRepository([100, 100, 17]);
    const service = new PurgeExpiredTripPlansService(repository);
    const before = new Date('2026-07-22T12:00:00.000Z');

    await expect(service.execute({ batchSize: 100, before })).resolves.toEqual({
      batches: 3,
      deleted: 217,
    });
    expect(repository.calls).toHaveLength(3);
  });

  it('stops at the configured batch ceiling', async () => {
    const repository = new StubTripPlanRepository([100, 100, 100]);
    const service = new PurgeExpiredTripPlansService(repository);

    await expect(
      service.execute({
        batchSize: 100,
        before: new Date('2026-07-22T12:00:00.000Z'),
        maximumBatches: 2,
      }),
    ).resolves.toEqual({ batches: 2, deleted: 200 });
    expect(repository.calls).toHaveLength(2);
  });
});
