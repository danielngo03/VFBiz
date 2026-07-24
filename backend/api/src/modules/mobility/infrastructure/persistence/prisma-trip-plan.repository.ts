import { Injectable } from '@nestjs/common';
import type { Prisma } from '../../../../generated/prisma/client';
import { PrismaService } from '../../../../platform/database/prisma.service';
import { TripPlanRepository } from '../../application/ports/trip-plan.repository';
import type { PersistedTripPlanRecord } from '../../application/services/trip-plan-persistence-mapper';

@Injectable()
export class PrismaTripPlanRepository extends TripPlanRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async save(record: PersistedTripPlanRecord): Promise<void> {
    await this.prisma.tripPlanProjection.create({
      data: {
        algorithmRevision: record.algorithmRevision,
        cachePolicy: record.cachePolicy,
        calculatedAt: record.calculatedAt,
        customerProfileId: record.customerProfileId,
        expiresAt: record.expiresAt,
        failureCode: record.failureCode,
        id: record.id,
        privacyClassification: record.privacyClassification,
        providerPayloadStored: record.providerPayloadStored,
        request: record.request as unknown as Prisma.InputJsonValue,
        requestFingerprint: record.requestFingerprint,
        requestSchema: record.requestSchema,
        result: record.result as unknown as Prisma.InputJsonValue,
        resultSchema: record.resultSchema,
        retentionUntil: record.retentionUntil,
        routeProvider: record.routeProvider,
        routeRequestHash: record.routeRequestHash,
        sourceRevisions: record.sourceRevisions,
        status: record.status,
        vehicleEnergyProfileId: record.vehicleEnergyProfileId,
        warnings: record.warnings,
      },
      select: { id: true },
    });
  }

  async deleteExpired(input: { before: Date; limit: number }): Promise<number> {
    return this.prisma.$transaction(async (transaction) => {
      const records = await transaction.tripPlanProjection.findMany({
        orderBy: { retentionUntil: 'asc' },
        select: { id: true },
        take: input.limit,
        where: { retentionUntil: { lte: input.before } },
      });
      if (records.length === 0) return 0;
      const deleted = await transaction.tripPlanProjection.deleteMany({
        where: { id: { in: records.map(({ id }) => id) } },
      });
      return deleted.count;
    });
  }
}
