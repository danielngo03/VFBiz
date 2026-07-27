import { Injectable } from '@nestjs/common';
import { PrismaService } from '../../../../platform/database/prisma.service';
import {
  WorkforceCustomerSupportRepository,
  type SearchWorkforceCustomersInput,
} from '../../application/ports/workforce-customer-support.repository';

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

@Injectable()
export class PrismaWorkforceCustomerSupportRepository extends WorkforceCustomerSupportRepository {
  constructor(private readonly prisma: PrismaService) {
    super();
  }

  async search(input: SearchWorkforceCustomersInput) {
    if (input.allowedMarkets !== null && input.allowedMarkets.length === 0) {
      return [];
    }
    // `id` is a native uuid column: Postgres rejects the query outright if a
    // non-UUID search term is bound against it, so the exact-ID branch is
    // only included when the term is actually UUID-shaped. Every other
    // query (the common case: searching by name) matches on displayName
    // alone.
    const records = await this.prisma.$transaction(async (transaction) => {
      const customers = await transaction.customerProfile.findMany({
        orderBy: [{ updatedAt: 'desc' }, { id: 'asc' }],
        select: {
          _count: { select: { garageEntries: true } },
          displayName: true,
          id: true,
          locale: true,
          market: true,
          status: true,
          updatedAt: true,
        },
        take: input.limit,
        where: {
          ...(input.allowedMarkets === null
            ? {}
            : { market: { in: [...input.allowedMarkets] } }),
          OR: UUID_PATTERN.test(input.query)
            ? [{ id: { equals: input.query } }]
            : [{ displayName: { contains: input.query, mode: 'insensitive' } }],
        },
      });
      await transaction.auditEvent.create({
        data: {
          action: 'customer-support.customer.searched',
          actorRef: input.actorRef,
          actorType: 'workforce',
          correlationId: input.correlationId,
          metadata: {
            resultCount: customers.length,
            searchTermHashOnly: true,
            reason: input.reason,
          },
          outcome: 'succeeded',
          resourceId: null,
          resourceType: 'customer_profile',
        },
      });
      return customers;
    });
    return records.map((record) => ({
      displayName: record.displayName,
      garageVehicleCount: record._count.garageEntries,
      id: record.id,
      locale: record.locale,
      market: record.market,
      status: record.status.toLowerCase() as 'active' | 'suspended' | 'deleted',
      updatedAt: record.updatedAt,
    }));
  }
}
