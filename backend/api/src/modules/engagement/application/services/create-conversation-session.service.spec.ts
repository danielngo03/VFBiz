import { describe, expect, it } from '@jest/globals';
import { CreateConversationSessionService } from './create-conversation-session.service';
import {
  ActiveAssistantReleaseProjection,
  type AssistantReleaseBinding,
} from '../ports/active-assistant-release-projection';
import {
  ConversationSessionRepository,
  type ConversationAccessRecord,
  type ConversationMessageView,
  type ConversationSessionSummary,
  type CreateConversationSessionRecordInput,
  type CreatedConversationSessionRecord,
} from '../ports/conversation-session.repository';
import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';

const release: AssistantReleaseBinding = {
  activationEnvelopeSha256: 'a'.repeat(64),
  activationId: 'activation-staging',
  effectiveAt: new Date('2026-08-03T00:00:00.000Z'),
  expiresAt: new Date('2026-08-04T00:00:00.000Z'),
  graphRevision: 'graph-v1',
  knowledgeRevision: 'knowledge-v1',
  manifestSha256: 'b'.repeat(64),
  pointerRevision: 1,
  policyRevision: 'policy-v1',
};

const principal: AccessPrincipal = {
  subject: 'customer-1',
  issuer: 'https://issuer.example',
  audience: ['customer'],
  authorizedParty: 'portal',
  realm: 'customer',
  scopes: ['chat:use'],
  sessionId: 'session-1',
  authenticationContext: null,
  authenticationMethods: ['pwd'],
};

class FakeReleaseProjection extends ActiveAssistantReleaseProjection {
  async resolve(): Promise<AssistantReleaseBinding> {
    await Promise.resolve();
    return release;
  }
}

class FakeSessionRepository extends ConversationSessionRepository {
  private readonly reservations = new Set<string>();

  async createSession(
    input: CreateConversationSessionRecordInput,
  ): Promise<CreatedConversationSessionRecord> {
    await Promise.resolve();
    if (input.subjectBudget !== null && input.subjectBudget !== undefined) {
      const key = `${input.subjectBudget.subjectKeyHash}:${input.subjectBudget.budgetDate.toISOString()}`;
      if (this.reservations.has(key)) {
        throw new Error('CUSTOMER_CHAT_DAILY_BUDGET_EXHAUSTED');
      }
      this.reservations.add(key);
    }
    return {
      createdAt: new Date('2026-08-03T00:00:00.000Z'),
      expiresAt: input.expiresAt,
      id: input.id,
      locale: input.locale,
      profile: input.profile,
      retentionUntil: input.retentionUntil,
    };
  }

  async findAccessRecord(
    _sessionId: string,
  ): Promise<ConversationAccessRecord | null> {
    await Promise.resolve();
    void _sessionId;
    return null;
  }

  async findSessionSummary(
    _sessionId: string,
  ): Promise<ConversationSessionSummary | null> {
    await Promise.resolve();
    void _sessionId;
    return null;
  }

  async listMessages(
    _sessionId: string,
    _scope: ConversationAccessScope,
  ): Promise<readonly ConversationMessageView[]> {
    await Promise.resolve();
    void _sessionId;
    void _scope;
    return [];
  }
}

describe('CreateConversationSessionService subject budget', () => {
  it('passes one atomic subject reservation and maps exhaustion to 429', async () => {
    const service = new CreateConversationSessionService(
      new FakeSessionRepository(),
      new FakeReleaseProjection(),
    );
    const input = {
      locale: 'vi' as const,
      now: new Date('2026-08-03T10:30:00.000Z'),
      principal,
      profile: 'authenticated_customer' as const,
    };

    await service.execute(input);
    await expect(service.execute(input)).rejects.toMatchObject({
      status: 429,
      response: {
        code: 'CUSTOMER_CHAT_DAILY_BUDGET_EXHAUSTED',
      },
    });
  });

  it('uses a new UTC budget bucket on the next day', async () => {
    const repository = new FakeSessionRepository();
    const service = new CreateConversationSessionService(
      repository,
      new FakeReleaseProjection(),
    );

    await service.execute({
      locale: 'vi',
      now: new Date('2026-08-03T23:59:59.000Z'),
      principal,
      profile: 'authenticated_customer',
    });
    await expect(
      service.execute({
        locale: 'vi',
        now: new Date('2026-08-04T00:00:00.000Z'),
        principal,
        profile: 'authenticated_customer',
      }),
    ).resolves.toBeDefined();
  });
});
