import { createHash } from 'node:crypto';
import { Test } from '@nestjs/testing';
import {
  FastifyAdapter,
  NestFastifyApplication,
} from '@nestjs/platform-fastify';
import { EngagementModule } from '../../../src/modules/engagement';
import {
  ConversationSessionRepository,
  type ConversationAccessRecord,
  type ConversationSessionSummary,
  type CreateConversationSessionRecordInput,
  type CreatedConversationSessionRecord,
} from '../../../src/modules/engagement/application/ports/conversation-session.repository';
import {
  ActiveAssistantReleaseProjection,
  type AssistantReleaseBinding,
} from '../../../src/modules/engagement/application/ports/active-assistant-release-projection';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import { PrismaService } from '../../../src/platform/database/prisma.service';
import { PlatformConfigModule } from '../../../src/platform/config/config.module';

const SESSION_ID = '2b6a6e9a-3b7a-4a0e-9f6a-6a2e2b9a6e1a';
const CAPABILITY = 'anonymous-chat-throttle-capability';
const TEST_NETWORK_OCTET = (process.pid % 200) + 1;
const SESSION_CREATION_IP = `198.51.100.${TEST_NETWORK_OCTET}`;
const MESSAGE_SUBMISSION_IP = `203.0.113.${TEST_NETWORK_OCTET}`;
const ACTIVE_RELEASE: AssistantReleaseBinding = {
  activationEnvelopeSha256: 'a'.repeat(64),
  activationId: '00000000-0000-4000-8000-000000000010',
  effectiveAt: new Date('2026-07-22T00:00:00.000Z'),
  expiresAt: new Date('2099-01-01T00:00:00.000Z'),
  graphRevision: 'conversation-graph-v1',
  knowledgeRevision: 'knowledge-v1',
  manifestSha256: 'b'.repeat(64),
  pointerRevision: 1,
  policyRevision: 'customer-grounded-v1',
};

class StubConversationSessionRepository implements ConversationSessionRepository {
  createSession(
    input: CreateConversationSessionRecordInput,
  ): Promise<CreatedConversationSessionRecord> {
    return Promise.resolve({
      createdAt: new Date('2026-07-22T12:00:00.000Z'),
      id: SESSION_ID,
      locale: input.locale,
      profile: input.profile,
    });
  }

  findAccessRecord(
    sessionId: string,
  ): Promise<ConversationAccessRecord | null> {
    if (sessionId !== SESSION_ID) return Promise.resolve(null);
    return Promise.resolve({
      capabilityHash: createHash('sha256').update(CAPABILITY).digest('hex'),
      customerSubject: null,
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
      createdAt: new Date('2026-07-22T12:00:00.000Z'),
      expiresAt: new Date('2099-01-01T00:00:00.000Z'),
      id: SESSION_ID,
      locale: 'vi',
      profile: 'public_customer',
      retentionUntil: new Date('2099-01-02T00:00:00.000Z'),
    });
  }

  listMessages(): Promise<readonly never[]> {
    return Promise.resolve([]);
  }
}

describe('conversation endpoint throttling (e2e)', () => {
  let app: NestFastifyApplication;

  beforeAll(async () => {
    const moduleFixture = await Test.createTestingModule({
      imports: [PlatformConfigModule, EngagementModule],
    })
      .overrideProvider(ActiveAssistantReleaseProjection)
      .useValue({
        resolve: () => Promise.resolve(ACTIVE_RELEASE),
      })
      .overrideProvider(ConversationSessionRepository)
      .useValue(new StubConversationSessionRepository())
      .overrideProvider(PrismaService)
      .useValue({})
      .compile();
    app = moduleFixture.createNestApplication<NestFastifyApplication>(
      new FastifyAdapter(),
    );
    await configureApplication(app);
    await app.init();
  });

  afterAll(async () => app.close());

  it('rejects anonymous session creation past the per-IP limit', async () => {
    const responses = [];
    for (let attempt = 0; attempt < 6; attempt += 1) {
      responses.push(
        await app.inject({
          method: 'POST',
          payload: { locale: 'vi', profile: 'public_customer' },
          remoteAddress: SESSION_CREATION_IP,
          url: '/api/v1/chat/sessions',
        }),
      );
    }

    const statusCodes = responses.map((response) => response.statusCode);
    expect(statusCodes.slice(0, 5)).toEqual([201, 201, 201, 201, 201]);
    expect(statusCodes[5]).toBe(429);
  });

  it('rejects message submission past the per-IP limit independently of session creation', async () => {
    const payload = {
      clientMessageId: '3c9f6b3a-2e7a-4b5f-8a1a-9b6d2e7a4c1a',
      content: 'Ping',
      expectedVersion: 0,
    };
    const responses = [];
    for (let attempt = 0; attempt < 21; attempt += 1) {
      responses.push(
        await app.inject({
          headers: {
            cookie: `__Host-vfbiz_chat=${SESSION_ID}.${CAPABILITY}`,
          },
          method: 'POST',
          payload,
          remoteAddress: MESSAGE_SUBMISSION_IP,
          url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
        }),
      );
    }

    const statusCodes = responses.map((response) => response.statusCode);
    // Each call is authorized and reaches the disabled-runtime check (503)
    // until the 21st, which the throttler must reject before that point.
    expect(statusCodes.slice(0, 20).every((code) => code === 503)).toBe(true);
    expect(statusCodes[20]).toBe(429);
  });
});
