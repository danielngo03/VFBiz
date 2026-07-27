import { randomUUID } from 'node:crypto';
import { ConfigService } from '@nestjs/config';
import { PrismaService } from '../../../src/platform/database/prisma.service';
import { PrismaWorkforceCustomerSupportRepository } from '../../../src/modules/customer/infrastructure/persistence/prisma-workforce-customer-support.repository';

const databaseUrl = process.env.VFBIZ_TEST_DATABASE_URL;
const describeWithDatabase =
  databaseUrl === undefined ? describe.skip : describe;

describeWithDatabase(
  'Workforce customer support search PostgreSQL integration',
  () => {
    let prisma: PrismaService;
    let repository: PrismaWorkforceCustomerSupportRepository;

    beforeAll(async () => {
      prisma = new PrismaService(
        new ConfigService({
          NODE_ENV: 'test',
          VFBIZ_DATABASE_URL: databaseUrl,
        }),
      );
      await prisma.$connect();
      repository = new PrismaWorkforceCustomerSupportRepository(prisma);
    });

    afterAll(async () => prisma.$disconnect());

    async function seedCustomer(displayName: string, market = 'VN') {
      const issuer = `https://identity.example/${randomUUID()}`;
      const subject = randomUUID();
      const identity = await prisma.identitySubject.create({
        data: { issuer, realm: 'vfbiz-customer', subject },
      });
      const profile = await prisma.customerProfile.create({
        data: { displayName, identitySubjectId: identity.id, market },
      });
      return { identity, profile };
    }

    async function cleanup(
      identity: { id: string },
      profile: { id: string },
    ): Promise<void> {
      await prisma.auditEvent.deleteMany({
        where: { resourceType: 'customer_profile' },
      });
      await prisma.customerProfile.delete({ where: { id: profile.id } });
      await prisma.identitySubject.delete({ where: { id: identity.id } });
    }

    it('persists exactly one audit event with a hash-only search term on a real search', async () => {
      const displayName = `Nguyen Search Integration ${randomUUID()}`;
      const { identity, profile } = await seedCustomer(displayName);
      const actorRef = `workforce-actor-${randomUUID()}`;
      const correlationId = randomUUID();
      const rawQuery = displayName;

      try {
        const results = await repository.search({
          actorRef,
          allowedMarkets: null,
          correlationId,
          limit: 20,
          query: rawQuery,
          reason: 'Resolve verified customer support case',
        });

        expect(results).toEqual([
          expect.objectContaining({ displayName, id: profile.id }),
        ]);

        const events = await prisma.auditEvent.findMany({
          where: { correlationId },
        });
        expect(events).toHaveLength(1);
        const [event] = events;
        expect(event).toMatchObject({
          action: 'customer-support.customer.searched',
          actorRef,
          actorType: 'workforce',
          correlationId,
          outcome: 'succeeded',
          resourceId: null,
          resourceType: 'customer_profile',
        });
        expect(JSON.stringify(event.metadata)).not.toContain(rawQuery);
        expect(event.metadata).toMatchObject({
          resultCount: 1,
          searchTermHashOnly: true,
        });
      } finally {
        await cleanup(identity, profile);
      }
    });

    it('finds a customer by exact ID without crashing on the uuid column', async () => {
      const displayName = `ID Search Integration ${randomUUID()}`;
      const { identity, profile } = await seedCustomer(displayName);
      const actorRef = `workforce-actor-${randomUUID()}`;
      const correlationId = randomUUID();

      try {
        const results = await repository.search({
          actorRef,
          allowedMarkets: null,
          correlationId,
          limit: 20,
          query: profile.id,
          reason: 'Resolve verified customer support case',
        });

        expect(results).toEqual([
          expect.objectContaining({ displayName, id: profile.id }),
        ]);
      } finally {
        await cleanup(identity, profile);
      }
    });

    it('still records an audit event when a search matches nothing', async () => {
      const actorRef = `workforce-actor-${randomUUID()}`;
      const correlationId = randomUUID();
      const rawQuery = `no-such-customer-${randomUUID()}`;

      const results = await repository.search({
        actorRef,
        allowedMarkets: null,
        correlationId,
        limit: 20,
        query: rawQuery,
        reason: 'Resolve verified customer support case',
      });

      expect(results).toEqual([]);
      const events = await prisma.auditEvent.findMany({
        where: { correlationId },
      });
      expect(events).toHaveLength(1);
      expect(events[0]?.metadata).toMatchObject({ resultCount: 0 });
      expect(JSON.stringify(events[0]?.metadata)).not.toContain(rawQuery);

      await prisma.auditEvent.deleteMany({ where: { correlationId } });
    });

    it('excludes a customer outside the allowed market scope, still auditing the attempt', async () => {
      const displayName = `Market Scoped Integration ${randomUUID()}`;
      const { identity, profile } = await seedCustomer(displayName, 'US');
      const actorRef = `workforce-actor-${randomUUID()}`;
      const correlationId = randomUUID();

      try {
        const results = await repository.search({
          actorRef,
          allowedMarkets: ['VN'],
          correlationId,
          limit: 20,
          query: displayName,
          reason: 'Resolve verified customer support case',
        });

        expect(results).toEqual([]);
        const events = await prisma.auditEvent.findMany({
          where: { correlationId },
        });
        expect(events).toHaveLength(1);
        expect(events[0]?.metadata).toMatchObject({ resultCount: 0 });
      } finally {
        await cleanup(identity, profile);
      }
    });
  },
);
