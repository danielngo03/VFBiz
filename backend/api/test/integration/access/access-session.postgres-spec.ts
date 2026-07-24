import { randomUUID } from 'node:crypto';
import { ConfigService } from '@nestjs/config';
import { PrismaAccessSessionRepository } from '../../../src/modules/access/infrastructure/persistence/prisma-access-session.repository';
import { PrismaService } from '../../../src/platform/database/prisma.service';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';
import { LocalSessionStatusVerifier } from '../../../src/platform/security/local-session-status.verifier';

const databaseUrl = process.env.VFBIZ_TEST_DATABASE_URL;
const describeWithDatabase =
  databaseUrl === undefined ? describe.skip : describe;

describeWithDatabase('Access session PostgreSQL integration', () => {
  let prisma: PrismaService;
  let repository: PrismaAccessSessionRepository;
  const issuer = 'https://id.example/realms/customer';
  const principal: AccessPrincipal = {
    authenticationContext: null,
    authenticationMethods: [],
    audience: ['vfbiz-api'],
    authorizedParty: 'vfbiz-customer-bff',
    issuer,
    realm: 'customer',
    scopes: ['session:read', 'session:revoke'],
    sessionId: 'opaque-session-a',
    subject: 'customer-a',
  };

  beforeAll(async () => {
    prisma = new PrismaService(
      new ConfigService({
        NODE_ENV: 'test',
        VFBIZ_DATABASE_URL: databaseUrl,
      }),
    );
    await prisma.$connect();
    repository = new PrismaAccessSessionRepository(prisma);
  });

  afterAll(async () => prisma.$disconnect());

  beforeEach(async () => {
    await prisma.sessionProjection.deleteMany({
      where: { identitySubject: { issuer } },
    });
    await prisma.identitySubject.deleteMany({ where: { issuer } });
  });

  async function seedSession(subject = principal.subject) {
    const now = new Date('2026-07-23T10:00:00Z');
    const observation = {
      authenticatedAt: new Date('2026-07-23T08:00:00Z'),
      authorizedParty: principal.authorizedParty,
      deviceLabel: 'Integration browser',
      emailVerified: true,
      eventRevision: 1n,
      expiresAt: new Date('2026-07-24T08:00:00Z'),
      issuer,
      ipPrefix: '127.0.0.0/24',
      lastSeenAt: new Date('2026-07-23T09:00:00Z'),
      mfaSatisfied: true,
      observedAt: new Date('2026-07-23T09:00:00Z'),
      providerRoute: 'customer-ciam' as const,
      providerSessionSecretReference: `secret://ciam/session/${randomUUID()}`,
      realm: 'customer' as const,
      revokedAt: null,
      sessionReference:
        subject === principal.subject
          ? principal.sessionId!
          : `opaque-${subject}`,
      subject,
      userAgentSummary: 'Integration browser',
    };
    const session = await repository.reconcile(observation, now);
    const identity = await prisma.identitySubject.findUniqueOrThrow({
      where: { issuer_subject: { issuer, subject } },
    });
    return { identity, now, observation, session };
  }

  it('atomically provisions identity and session from the first observation', async () => {
    const { identity, session } = await seedSession();

    expect(identity.realm).toBe('customer');
    expect(session.isCurrent).toBe(true);
    await expect(
      prisma.sessionProjection.count({
        where: { identitySubjectId: identity.id },
      }),
    ).resolves.toBe(1);
  });

  it('isolates sessions by verified issuer and subject', async () => {
    await seedSession();
    await seedSession('customer-b');

    const sessions = await repository.list(
      principal,
      new Date('2026-07-23T10:00:00Z'),
    );

    expect(sessions).toHaveLength(1);
    expect(sessions[0]?.isCurrent).toBe(true);
  });

  it('allows only one concurrent revocation dispatcher and denies locally', async () => {
    const { session } = await seedSession();
    const now = new Date('2026-07-23T10:00:00Z');

    const attempts = await Promise.all([
      repository.beginRevocation(principal, session.id, now),
      repository.beginRevocation(principal, session.id, now),
    ]);

    expect(attempts.filter((attempt) => attempt.dispatch)).toHaveLength(1);
    await expect(
      new LocalSessionStatusVerifier(prisma).isDenied(principal, now),
    ).resolves.toBe(true);
  });

  it('denies the current session immediately on local logout', async () => {
    await seedSession();
    const now = new Date('2026-07-23T10:00:00Z');

    await repository.revokeCurrent(principal, now);

    await expect(
      new LocalSessionStatusVerifier(prisma).isDenied(principal, now),
    ).resolves.toBe(true);
  });

  it('ignores stale observations and preserves the trusted provider reference', async () => {
    const { observation, session } = await seedSession();
    await repository.reconcile(
      {
        ...observation,
        deviceLabel: 'New trusted label',
        eventRevision: 3n,
        providerSessionSecretReference: 'secret://ciam/session/revision-3',
      },
      new Date('2026-07-23T10:00:00Z'),
    );
    await repository.reconcile(
      {
        ...observation,
        deviceLabel: 'Stale label',
        eventRevision: 2n,
        providerSessionSecretReference: 'secret://ciam/session/revision-2',
      },
      new Date('2026-07-23T10:00:00Z'),
    );

    const persisted = await prisma.sessionProjection.findUniqueOrThrow({
      where: { id: session.id },
    });
    expect(persisted.deviceLabel).toBe('New trusted label');
    expect(persisted.observationRevision).toBe(3n);
    expect(persisted.providerSessionSecretReference).toBe(
      'secret://ciam/session/revision-3',
    );
  });
});
