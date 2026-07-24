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
  type CreateConversationSessionRecordInput,
  type CreatedConversationSessionRecord,
} from '../../../src/modules/engagement/application/ports/conversation-session.repository';
import { configureApplication } from '../../../src/bootstrap/configure-application';
import { PrismaService } from '../../../src/platform/database/prisma.service';
import { PlatformConfigModule } from '../../../src/platform/config/config.module';

const SESSION_ID = '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb';
const CAPABILITY = 'anonymous-chat-capability';

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

  listMessages(): Promise<readonly never[]> {
    return Promise.resolve([]);
  }
}

describe('conversation object authorization (e2e)', () => {
  let app: NestFastifyApplication;

  beforeAll(async () => {
    const moduleFixture = await Test.createTestingModule({
      imports: [PlatformConfigModule, EngagementModule],
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

  it('creates an anonymous session and issues a secure session-bound cookie', async () => {
    const response = await app.inject({
      method: 'POST',
      payload: { locale: 'vi', profile: 'public_customer' },
      url: '/api/v1/chat/sessions',
    });

    expect(response.statusCode).toBe(201);
    expect(response.json()).toMatchObject({
      id: SESSION_ID,
      locale: 'vi',
      profile: 'public_customer',
    });
    expect(response.headers['set-cookie']).toMatch(
      new RegExp(
        `^__Host-vfbiz_chat=${SESSION_ID}\\.[A-Za-z0-9_-]+; Max-Age=1800; Path=/; HttpOnly; Secure; SameSite=Lax$`,
      ),
    );
    expect(response.headers['cache-control']).toBe('no-store');
  });

  it('rejects an authenticated profile when no verified principal exists', async () => {
    const response = await app.inject({
      method: 'POST',
      payload: { locale: 'vi', profile: 'authenticated_customer' },
      url: '/api/v1/chat/sessions',
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({
      code: 'AUTHENTICATED_CHAT_REQUIRES_CUSTOMER',
    });
  });

  it('denies message history without the session-bound capability', async () => {
    const response = await app.inject({
      method: 'GET',
      url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
    });

    expect(response.statusCode).toBe(403);
    expect(response.json()).toMatchObject({ code: 'CHAT_SESSION_FORBIDDEN' });
  });

  it('allows message history with the session-bound HttpOnly cookie value', async () => {
    const response = await app.inject({
      headers: {
        cookie: `__Host-vfbiz_chat=${SESSION_ID}.${CAPABILITY}`,
      },
      method: 'GET',
      url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
    });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual([]);
    expect(response.headers['cache-control']).toBe('no-store');
  });

  it('does not allow a valid capability to be replayed for another session', async () => {
    const response = await app.inject({
      headers: {
        cookie: `__Host-vfbiz_chat=${SESSION_ID}.${CAPABILITY}`,
      },
      method: 'GET',
      url: '/api/v1/chat/sessions/664aa870-1ae6-457f-9e36-b7853a2ab77f/messages',
    });

    expect(response.statusCode).toBe(403);
  });

  it('authorizes message submission before exposing the unavailable AI runtime', async () => {
    const denied = await app.inject({
      method: 'POST',
      payload: { content: 'VF 8 có phạm vi hoạt động bao nhiêu?' },
      url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
    });
    expect(denied.statusCode).toBe(403);

    const authorized = await app.inject({
      headers: {
        cookie: `__Host-vfbiz_chat=${SESSION_ID}.${CAPABILITY}`,
      },
      method: 'POST',
      payload: { content: 'VF 8 có phạm vi hoạt động bao nhiêu?' },
      url: `/api/v1/chat/sessions/${SESSION_ID}/messages`,
    });
    expect(authorized.statusCode).toBe(503);
    expect(authorized.json()).toMatchObject({
      code: 'CHAT_RUNTIME_UNAVAILABLE',
    });
  });

  afterAll(async () => app.close());
});
