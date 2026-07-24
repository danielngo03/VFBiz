import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { ForbiddenException, Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import {
  ConversationSessionRepository,
  type CreatedConversationSessionRecord,
} from '../ports/conversation-session.repository';

export interface CreateConversationSessionInput {
  readonly locale: 'vi' | 'en';
  readonly now?: Date;
  readonly principal: AccessPrincipal | null;
  readonly profile: 'public_customer' | 'authenticated_customer';
}

export interface CreatedConversationSession {
  readonly capability: string | null;
  readonly expiresInSeconds: number;
  readonly session: CreatedConversationSessionRecord;
}

const SESSION_TTL_SECONDS = 30 * 60;
const RETENTION_SECONDS = 24 * 60 * 60;

@Injectable()
export class CreateConversationSessionService {
  constructor(private readonly sessions: ConversationSessionRepository) {}

  async execute(
    input: CreateConversationSessionInput,
  ): Promise<CreatedConversationSession> {
    if (
      input.profile === 'authenticated_customer' &&
      input.principal === null
    ) {
      throw new ForbiddenException({
        code: 'AUTHENTICATED_CHAT_REQUIRES_CUSTOMER',
        message: 'An authenticated customer session is required.',
      });
    }

    const now = input.now ?? new Date();
    const capability =
      input.profile === 'public_customer'
        ? randomBytes(32).toString('base64url')
        : null;
    const session = await this.sessions.createSession({
      capabilityHash:
        capability === null
          ? null
          : createHash('sha256').update(capability, 'utf8').digest('hex'),
      customerSubject:
        input.principal === null
          ? null
          : {
              issuer: input.principal.issuer,
              subject: input.principal.subject,
            },
      expiresAt: new Date(now.getTime() + SESSION_TTL_SECONDS * 1000),
      id: randomUUID(),
      locale: input.locale,
      policyRevision: 'customer-chat-policy-v1',
      profile: input.profile,
      retentionUntil: new Date(now.getTime() + RETENTION_SECONDS * 1000),
    });
    return {
      capability,
      expiresInSeconds: SESSION_TTL_SECONDS,
      session,
    };
  }
}
