import { randomUUID } from 'node:crypto';
import { ConfigService } from '@nestjs/config';
import { PrismaIdempotencyRepository } from '../../../src/modules/access/infrastructure/persistence/prisma-idempotency.repository';
import { PrismaService } from '../../../src/platform/database/prisma.service';

const databaseUrl = process.env.VFBIZ_TEST_DATABASE_URL;
const describeWithDatabase =
  databaseUrl === undefined ? describe.skip : describe;

describeWithDatabase('Idempotency PostgreSQL integration', () => {
  let prisma: PrismaService;
  let repository: PrismaIdempotencyRepository;
  const namespace = 'workforce.role.create.integration-test';

  beforeAll(async () => {
    prisma = new PrismaService(
      new ConfigService({
        NODE_ENV: 'test',
        VFBIZ_DATABASE_URL: databaseUrl,
      }),
    );
    await prisma.$connect();
    repository = new PrismaIdempotencyRepository(prisma);
  });

  afterAll(async () => prisma.$disconnect());

  beforeEach(async () => {
    await prisma.idempotencyRecord.deleteMany({ where: { namespace } });
  });

  it('reserves a fresh key and lets the caller complete it', async () => {
    const key = randomUUID();
    const requestHash = 'a'.repeat(64);

    const reservation = await repository.reserve({
      namespace,
      key,
      requestHash,
      ttlSeconds: 3600,
    });

    expect(reservation).toEqual({ kind: 'reserved' });

    await repository.complete({
      namespace,
      key,
      responseStatus: 201,
      responseBody: { roleId: 'role-1' },
    });

    const stored = await prisma.idempotencyRecord.findFirst({
      where: { namespace },
    });
    expect(stored?.status).toBe('completed');
    expect(stored?.responseStatus).toBe(201);
    expect(stored?.responseBody).toEqual({ roleId: 'role-1' });
  });

  it('replays the exact cached response for the same key and request', async () => {
    const key = randomUUID();
    const requestHash = 'b'.repeat(64);

    await repository.reserve({ namespace, key, requestHash, ttlSeconds: 3600 });
    await repository.complete({
      namespace,
      key,
      responseStatus: 201,
      responseBody: { roleId: 'role-2' },
    });

    const replay = await repository.reserve({
      namespace,
      key,
      requestHash,
      ttlSeconds: 3600,
    });

    expect(replay).toEqual({
      kind: 'replay',
      responseStatus: 201,
      responseBody: { roleId: 'role-2' },
    });
  });

  it('conflicts when the same key is reused for a different request', async () => {
    const key = randomUUID();

    await repository.reserve({
      namespace,
      key,
      requestHash: 'c'.repeat(64),
      ttlSeconds: 3600,
    });
    await repository.complete({
      namespace,
      key,
      responseStatus: 201,
      responseBody: { roleId: 'role-3' },
    });

    const reused = await repository.reserve({
      namespace,
      key,
      requestHash: 'd'.repeat(64),
      ttlSeconds: 3600,
    });

    expect(reused).toEqual({ kind: 'conflict' });
  });

  it('conflicts on a duplicate in-flight request that has not completed yet', async () => {
    const key = randomUUID();
    const requestHash = 'e'.repeat(64);

    await repository.reserve({ namespace, key, requestHash, ttlSeconds: 3600 });
    const duplicate = await repository.reserve({
      namespace,
      key,
      requestHash,
      ttlSeconds: 3600,
    });

    expect(duplicate).toEqual({ kind: 'conflict' });
  });

  it('allows only one concurrent reservation to win for the same key', async () => {
    const key = randomUUID();
    const requestHash = 'f'.repeat(64);

    const attempts = await Promise.all([
      repository.reserve({ namespace, key, requestHash, ttlSeconds: 3600 }),
      repository.reserve({ namespace, key, requestHash, ttlSeconds: 3600 }),
      repository.reserve({ namespace, key, requestHash, ttlSeconds: 3600 }),
    ]);

    const reserved = attempts.filter((attempt) => attempt.kind === 'reserved');
    const conflicted = attempts.filter(
      (attempt) => attempt.kind === 'conflict',
    );
    expect(reserved).toHaveLength(1);
    expect(conflicted).toHaveLength(2);
  });

  it('reclaims a pending reservation once its TTL has elapsed instead of conflicting forever', async () => {
    const key = randomUUID();
    const requestHash = 'a3'.repeat(32);

    const first = await repository.reserve({
      namespace,
      key,
      requestHash,
      ttlSeconds: -1,
    });
    expect(first).toEqual({ kind: 'reserved' });
    // The reservation is never completed here, simulating a worker that
    // crashed before calling `complete()`. Its TTL already elapsed
    // (ttlSeconds: -1), so it must be reclaimable rather than a permanent
    // conflict.

    const reclaimed = await repository.reserve({
      namespace,
      key,
      requestHash,
      ttlSeconds: 3600,
    });

    expect(reclaimed).toEqual({ kind: 'reserved' });

    const row = await prisma.idempotencyRecord.findFirst({
      where: { namespace },
    });
    expect(row?.status).toBe('pending');
    expect(row?.responseStatus).toBeNull();
    expect(row?.responseBody).toBeNull();
    expect(row?.expiresAt.getTime()).toBeGreaterThan(Date.now());
  });

  it('scopes keys by namespace so the same key in a different namespace is independent', async () => {
    const key = randomUUID();
    const requestHash = 'a1'.repeat(32);
    const otherNamespace = `${namespace}.other`;

    await repository.reserve({ namespace, key, requestHash, ttlSeconds: 3600 });
    const inOtherNamespace = await repository.reserve({
      namespace: otherNamespace,
      key,
      requestHash,
      ttlSeconds: 3600,
    });

    expect(inOtherNamespace).toEqual({ kind: 'reserved' });
    await prisma.idempotencyRecord.deleteMany({
      where: { namespace: otherNamespace },
    });
  });
});
