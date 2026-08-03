import { createHash } from 'node:crypto';
import { type ExecutionContext } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { ConfigModule } from '@nestjs/config';
import {
  FastifyAdapter,
  type NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { Test } from '@nestjs/testing';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import { EngagementModule } from '../../../src/modules/engagement';
import { ActiveAssistantReleaseProjection } from '../../../src/modules/engagement/application/ports/active-assistant-release-projection';
import type { AssistantReleaseBinding } from '../../../src/modules/engagement/application/ports/active-assistant-release-projection';
import {
  ConversationSessionRepository,
  type ConversationAccessRecord,
  type ConversationSessionSummary,
  type CreateConversationSessionRecordInput,
  type CreatedConversationSessionRecord,
} from '../../../src/modules/engagement/application/ports/conversation-session.repository';
import { PrismaService } from '../../../src/platform/database/prisma.service';
import { RedisConnectionService } from '../../../src/platform/redis/redis-connection.service';
import type { AccessPrincipal } from '../../../src/platform/security/access-principal';

const SESSION_ID = 'bba2fd57-94d6-4c77-a6a7-2f4725bf9e64';
const TURN_ID = 'f7711397-8190-4a9e-b4b3-4e9b91fe2d1a';
const CUSTOMER_ISSUER = 'https://identity.example.test/customer';
const CONTROL_ID = 'staging-chat-control-e2e';
const AUTHORITY_DIGEST = 'a'.repeat(64);
const GENERATION = 9;
const now = Date.now();
const NOT_BEFORE = new Date(Math.floor((now - 60_000) / 1_000) * 1_000);
const EXPIRES_AT = new Date(Math.floor((now + 60 * 60_000) / 1_000) * 1_000);
const CONTROL_ID_DIGEST = createHash('sha256')
  .update(CONTROL_ID, 'utf8')
  .digest('hex');
const RELEASE_ENVELOPE_SHA256 = 'c'.repeat(64);
const RELEASE_POINTER_REVISION = 11;

const activeRelease = {
  activationEnvelopeSha256: RELEASE_ENVELOPE_SHA256,
  activationId: 'activation-staging-11',
  effectiveAt: NOT_BEFORE,
  expiresAt: EXPIRES_AT,
  graphRevision: 'graph-v1',
  knowledgeRevision: 'knowledge-v1',
  manifestSha256: 'd'.repeat(64),
  pointerRevision: RELEASE_POINTER_REVISION,
  policyRevision: 'policy-v1',
} satisfies AssistantReleaseBinding;

const configuredEnvironment = {
  NODE_ENV: 'test',
  VFBIZ_CHAT_API_MODE: 'authenticated-staging',
  VFBIZ_CHAT_LIVE_CONTROL_AUTHORITY_SHA256: AUTHORITY_DIGEST,
  VFBIZ_CHAT_LIVE_CONTROL_EXPIRES_AT: utcSeconds(EXPIRES_AT),
  VFBIZ_CHAT_LIVE_CONTROL_GENERATION: GENERATION,
  VFBIZ_CHAT_LIVE_CONTROL_ID: CONTROL_ID,
  VFBIZ_CHAT_LIVE_CONTROL_NOT_BEFORE: utcSeconds(NOT_BEFORE),
  VFBIZ_CHAT_LIVE_CONTROL_RELEASE_ENVELOPE_SHA256: RELEASE_ENVELOPE_SHA256,
  VFBIZ_CHAT_LIVE_CONTROL_RELEASE_POINTER_REVISION: RELEASE_POINTER_REVISION,
  VFBIZ_CUSTOMER_OIDC_AUDIENCE: 'vfbiz-customer-api',
  VFBIZ_CUSTOMER_OIDC_AUTHORIZED_PARTIES: 'vfbiz-customer-bff,vfbiz-mobile',
  VFBIZ_CUSTOMER_OIDC_ISSUER: CUSTOMER_ISSUER,
  VFBIZ_INTERNAL_AI_ASSERTION_AUDIENCE: 'vfbiz-ai',
  VFBIZ_INTERNAL_AI_ASSERTION_ISSUER: 'vfbiz-api',
  VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS: 30,
  VFBIZ_INTERNAL_AI_DISPATCH_ENABLED: false,
  VFBIZ_INTERNAL_AI_ENABLED: false,
  VFBIZ_INTERNAL_AI_REQUEST_TIMEOUT_MS: 15_000,
  VFBIZ_INTERNAL_AI_RETRY_BUDGET: 1,
};

const liveSnapshot = {
  authority_digest: AUTHORITY_DIGEST,
  control_id_digest: CONTROL_ID_DIGEST,
  enabled: '1',
  expires_at_ms: String(EXPIRES_AT.getTime()),
  generation: String(GENERATION),
  not_before_ms: String(NOT_BEFORE.getTime()),
  schema_version: 'vfbiz-staging-chat-live-control/v1',
};

function principal(): AccessPrincipal {
  return {
    authenticationContext: null,
    authenticationMethods: [],
    audience: ['vfbiz-customer-api'],
    authorizedParty: 'vfbiz-customer-bff',
    issuer: CUSTOMER_ISSUER,
    realm: 'customer',
    roles: [],
    scopes: ['chat:use'],
    sessionId: null,
    subject: 'customer-1',
  };
}

function injectTestPrincipal(context: ExecutionContext): boolean {
  const request = context.switchToHttp().getRequest<{
    headers: Record<string, string | string[] | undefined>;
    vfbizPrincipal?: AccessPrincipal;
  }>();
  const selected = request.headers['x-test-principal'];
  if (selected === 'customer') {
    request.vfbizPrincipal = principal();
  } else if (selected === 'workforce') {
    request.vfbizPrincipal = {
      ...principal(),
      issuer: 'https://identity.example.test/workforce',
      realm: 'workforce',
    };
  }
  return true;
}

class StubConversationSessionRepository implements ConversationSessionRepository {
  createSession(
    input: CreateConversationSessionRecordInput,
  ): Promise<CreatedConversationSessionRecord> {
    return Promise.resolve({
      createdAt: new Date('2026-08-01T00:00:00.000Z'),
      expiresAt: input.expiresAt,
      id: SESSION_ID,
      locale: input.locale,
      profile: input.profile,
      retentionUntil: input.retentionUntil,
    });
  }

  findAccessRecord(
    sessionId: string,
  ): Promise<ConversationAccessRecord | null> {
    if (sessionId !== SESSION_ID) return Promise.resolve(null);
    return Promise.resolve({
      capabilityHash: null,
      customerSubject: {
        issuer: CUSTOMER_ISSUER,
        subject: 'customer-1',
      },
      expiresAt: new Date('2099-01-01T00:00:00.000Z'),
      id: SESSION_ID,
      status: 'active',
    });
  }

  findSessionSummary(
    sessionId: string,
  ): Promise<ConversationSessionSummary | null> {
    if (sessionId !== SESSION_ID) return Promise.resolve(null);
    return Promise.resolve({
      createdAt: new Date('2026-08-01T00:00:00.000Z'),
      expiresAt: new Date('2099-01-01T00:00:00.000Z'),
      id: SESSION_ID,
      locale: 'vi',
      profile: 'authenticated_customer',
      retentionUntil: new Date('2099-01-02T00:00:00.000Z'),
    });
  }

  listMessages(): Promise<readonly never[]> {
    return Promise.resolve([]);
  }
}

describe('authenticated staging Chat live control (e2e)', () => {
  let app: NestFastifyApplication;
  let observedSnapshot: Record<string, string> | Error;
  let observedRelease: AssistantReleaseBinding | null;
  let hgetall: jest.Mock<Promise<Record<string, string>>, [string]>;

  beforeAll(async () => {
    observedSnapshot = { ...liveSnapshot };
    hgetall = jest.fn<Promise<Record<string, string>>, [string]>(() =>
      observedSnapshot instanceof Error
        ? Promise.reject(observedSnapshot)
        : Promise.resolve({ ...observedSnapshot }),
    );
    const redis = {
      client: { hgetall },
      ensureConnected: jest.fn(() => Promise.resolve()),
    } as unknown as RedisConnectionService;

    const moduleFixture = await Test.createTestingModule({
      imports: [
        ConfigModule.forRoot({
          ignoreEnvFile: true,
          isGlobal: true,
          load: [() => configuredEnvironment],
        }),
        EngagementModule,
      ],
      providers: [
        {
          provide: APP_GUARD,
          useValue: { canActivate: injectTestPrincipal },
        },
      ],
    })
      .overrideProvider(RedisConnectionService)
      .useValue(redis)
      .overrideProvider(ConversationSessionRepository)
      .useValue(new StubConversationSessionRepository())
      .overrideProvider(ActiveAssistantReleaseProjection)
      .useValue({ resolve: () => Promise.resolve(observedRelease) })
      .overrideProvider(PrismaService)
      .useValue({})
      .compile();

    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );
    await configureApplication(app);
    await app.init();
  });

  beforeEach(() => {
    observedSnapshot = { ...liveSnapshot };
    observedRelease = activeRelease;
    hgetall.mockClear();
  });

  afterAll(async () => app.close());

  it('runs authentication before consulting live control', async () => {
    const response = await app.inject({
      method: 'GET',
      url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
    });

    expect(response.statusCode).toBe(401);
    expect(hgetall).not.toHaveBeenCalled();
  });

  it.each([
    ['workforce', 403],
    ['public-capability', 401],
  ])('rejects %s before consulting live control', async (selected, status) => {
    const response = await app.inject({
      headers: {
        cookie: '__Host-vfbiz_chat=opaque.public.capability',
        'x-test-principal': selected,
      },
      method: 'GET',
      url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
    });

    expect(response.statusCode).toBe(status);
    expect(hgetall).not.toHaveBeenCalled();
  });

  it('fails closed through the assembled guard on every Chat route', async () => {
    observedSnapshot = { ...liveSnapshot, enabled: '0' };
    const requests = [
      {
        method: 'POST' as const,
        payload: { locale: 'vi' },
        url: '/api/v1/chat/sessions',
      },
      {
        method: 'GET' as const,
        url: `/api/v1/chat/sessions/${SESSION_ID}`,
      },
      {
        method: 'GET' as const,
        url: `/api/v1/chat/sessions/${SESSION_ID}/events`,
      },
      {
        method: 'GET' as const,
        url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
      },
      {
        method: 'POST' as const,
        payload: {},
        url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
      },
      {
        method: 'POST' as const,
        payload: {},
        url: `/api/v1/chat/sessions/${SESSION_ID}/turns/${TURN_ID}/cancel`,
      },
      {
        method: 'POST' as const,
        payload: {},
        url: `/api/v1/chat/sessions/${SESSION_ID}/close`,
      },
      {
        method: 'POST' as const,
        payload: {},
        url: `/api/v1/chat/sessions/${SESSION_ID}/handoff`,
      },
    ];

    for (const request of requests) {
      const response = await app.inject({
        ...request,
        headers: { 'x-test-principal': 'customer' },
      });
      expect(response.statusCode).toBe(503);
      expect(response.json()).toMatchObject({
        code: 'CHAT_LIVE_CONTROL_CLOSED',
      });
    }
    expect(hgetall).toHaveBeenCalledTimes(requests.length);
  });

  it('applies disable on the immediately next request', async () => {
    await expectOwnerHistory(200);
    observedSnapshot = { ...liveSnapshot, enabled: '0' };
    await expectOwnerHistory(503);
    expect(hgetall).toHaveBeenCalledTimes(2);
  });

  it('rejects replay of the old enabled Redis snapshot after release revocation', async () => {
    await expectOwnerHistory(200);
    observedSnapshot = { ...liveSnapshot, enabled: '0' };
    observedRelease = null;
    await expectOwnerHistory(503);
    observedSnapshot = { ...liveSnapshot };
    await expectOwnerHistory(503);
    expect(hgetall).toHaveBeenCalledTimes(3);
  });

  it.each([
    ['generation', { ...liveSnapshot, generation: String(GENERATION + 1) }],
    ['authority digest', { ...liveSnapshot, authority_digest: 'b'.repeat(64) }],
  ])(
    'applies %s rotation on the immediately next request',
    async (_name, rotated) => {
      await expectOwnerHistory(200);
      observedSnapshot = rotated;
      await expectOwnerHistory(503);
      expect(hgetall).toHaveBeenCalledTimes(2);
    },
  );

  it('sanitizes a Redis outage on the immediately next request', async () => {
    await expectOwnerHistory(200);
    observedSnapshot = new Error(
      'redis://operator:credential@internal-cache.example:6379',
    );
    const response = await expectOwnerHistory(503);
    expect(response.body).not.toContain('redis');
    expect(response.body).not.toContain('credential');
    expect(hgetall).toHaveBeenCalledTimes(2);
  });

  async function expectOwnerHistory(expectedStatus: number) {
    const response = await app.inject({
      headers: { 'x-test-principal': 'customer' },
      method: 'GET',
      url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
    });
    expect(response.statusCode).toBe(expectedStatus);
    if (expectedStatus === 503) {
      expect(response.json()).toMatchObject({
        code: 'CHAT_LIVE_CONTROL_CLOSED',
      });
    }
    return response;
  }
});

function utcSeconds(value: Date): string {
  return value.toISOString().replace('.000Z', 'Z');
}
