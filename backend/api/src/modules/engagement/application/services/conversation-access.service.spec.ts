import { createHash } from 'node:crypto';
import {
  ConversationAccessDeniedError,
  ConversationAccessService,
} from './conversation-access.service';
import type {
  ConversationAccessRecord,
  ConversationSessionRepository,
} from '../ports/conversation-session.repository';

class StubConversationSessionRepository implements ConversationSessionRepository {
  constructor(private readonly record: ConversationAccessRecord | null) {}

  findAccessRecord(): Promise<ConversationAccessRecord | null> {
    return Promise.resolve(this.record);
  }

  createSession(): Promise<never> {
    return Promise.reject(new Error('Not used in this test.'));
  }

  listMessages(): Promise<readonly never[]> {
    return Promise.resolve([]);
  }
}

const hash = (value: string): string =>
  createHash('sha256').update(value).digest('hex');

describe('ConversationAccessService', () => {
  const now = new Date('2026-07-22T12:00:00.000Z');

  it('authorizes an active anonymous session only with its capability', async () => {
    const repository = new StubConversationSessionRepository({
      capabilityHash: hash('correct-capability'),
      customerSubject: null,
      expiresAt: new Date('2026-07-22T12:30:00.000Z'),
      id: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
      status: 'active',
    });
    const service = new ConversationAccessService(repository);

    await expect(
      service.authorize({
        capability: 'correct-capability',
        now,
        principal: null,
        sessionId: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
      }),
    ).resolves.toEqual({ accessMode: 'anonymous-capability' });
  });

  it.each([null, 'wrong-capability'])(
    'denies an anonymous session when capability is %s',
    async (capability) => {
      const repository = new StubConversationSessionRepository({
        capabilityHash: hash('correct-capability'),
        customerSubject: null,
        expiresAt: new Date('2026-07-22T12:30:00.000Z'),
        id: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
        status: 'active',
      });
      const service = new ConversationAccessService(repository);

      await expect(
        service.authorize({
          capability,
          now,
          principal: null,
          sessionId: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
        }),
      ).rejects.toBeInstanceOf(ConversationAccessDeniedError);
    },
  );

  it('denies an expired session even when its capability matches', async () => {
    const repository = new StubConversationSessionRepository({
      capabilityHash: hash('correct-capability'),
      customerSubject: null,
      expiresAt: new Date('2026-07-22T11:59:59.000Z'),
      id: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
      status: 'active',
    });
    const service = new ConversationAccessService(repository);

    await expect(
      service.authorize({
        capability: 'correct-capability',
        now,
        principal: null,
        sessionId: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
      }),
    ).rejects.toBeInstanceOf(ConversationAccessDeniedError);
  });

  it('authorizes only the matching OIDC subject for an authenticated session', async () => {
    const repository = new StubConversationSessionRepository({
      capabilityHash: null,
      customerSubject: {
        issuer: 'https://ciam.example/realms/customer',
        subject: 'customer-123',
      },
      expiresAt: new Date('2026-07-22T12:30:00.000Z'),
      id: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
      status: 'active',
    });
    const service = new ConversationAccessService(repository);

    await expect(
      service.authorize({
        capability: null,
        now,
        principal: {
          authenticationContext: 'urn:vfbiz:loa:1',
          authenticationMethods: ['pwd'],
          audience: ['vfbiz-api'],
          authorizedParty: 'vfbiz-customer-bff',
          issuer: 'https://ciam.example/realms/customer',
          realm: 'customer',
          scopes: ['chat:read'],
          sessionId: 'session-123',
          subject: 'customer-123',
        },
        sessionId: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
      }),
    ).resolves.toEqual({ accessMode: 'authenticated-subject' });

    await expect(
      service.authorize({
        capability: null,
        now,
        principal: {
          authenticationContext: 'urn:vfbiz:loa:1',
          authenticationMethods: ['pwd'],
          audience: ['vfbiz-api'],
          authorizedParty: 'vfbiz-customer-bff',
          issuer: 'https://ciam.example/realms/customer',
          realm: 'customer',
          scopes: ['chat:read'],
          sessionId: 'session-123',
          subject: 'another-customer',
        },
        sessionId: '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
      }),
    ).rejects.toBeInstanceOf(ConversationAccessDeniedError);
  });
});
