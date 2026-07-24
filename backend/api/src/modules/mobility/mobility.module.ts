import { Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { DatabaseModule } from '../../platform/database/database.module';
import { TripPlanRepository } from './application/ports/trip-plan.repository';
import { PersistTripPlanService } from './application/services/persist-trip-plan.service';
import { PurgeExpiredTripPlansService } from './application/services/purge-expired-trip-plans.service';
import { TripPlanPersistenceMapper } from './application/services/trip-plan-persistence-mapper';
import { PrismaTripPlanRepository } from './infrastructure/persistence/prisma-trip-plan.repository';

@Module({
  imports: [DatabaseModule],
  providers: [
    PersistTripPlanService,
    PurgeExpiredTripPlansService,
    {
      inject: [ConfigService],
      provide: TripPlanPersistenceMapper,
      useFactory: (config: ConfigService) =>
        new TripPlanPersistenceMapper(
          config.getOrThrow<string>('VFBIZ_TRIP_PSEUDONYMIZATION_KEY'),
        ),
    },
    {
      provide: TripPlanRepository,
      useClass: PrismaTripPlanRepository,
    },
  ],
  exports: [PersistTripPlanService, PurgeExpiredTripPlansService],
})
export class MobilityModule {}
