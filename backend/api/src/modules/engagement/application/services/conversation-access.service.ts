import { createHash, timingSafeEqual } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { ConversationSessionRepository } from '../ports/conversation-session.repository';
import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';

export class ConversationAccessDeniedError extends Error {
  constructor() {
    super('Conversation session access was denied.');
    this.name = 'ConversationAccessDeniedError';
  }
}

export interface AuthorizeConversationInput {
  readonly capability: string | null;
  readonly now: Date;
  readonly principal: AccessPrincipal | null;
  readonly sessionId: string;
}

export interface ConversationAuthorization {
  readonly accessScope: ConversationAccessScope;
  readonly accessMode: 'anonymous-capability' | 'authenticated-subject';
}

function hashCapability(capability: string): Buffer {
  return createHash('sha256').update(capability, 'utf8').digest();
}

function capabilityMatches(
  capability: string | null,
  expectedHexHash: string | null,
): boolean {
  if (capability === null || expectedHexHash === null) return false;
  const expected = Buffer.from(expectedHexHash, 'hex');
  const actual = hashCapability(capability);
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

@Injectable()
export class ConversationAccessService {
  constructor(private readonly sessions: ConversationSessionRepository) {}

  async authorize(
    input: AuthorizeConversationInput,
  ): Promise<ConversationAuthorization> {
    const record = await this.sessions.findAccessRecord(input.sessionId);
    if (
      record === null ||
      record.status !== 'active' ||
      record.expiresAt.getTime() <= input.now.getTime()
    ) {
      throw new ConversationAccessDeniedError();
    }

    if (record.customerSubject !== null) {
      if (
        input.principal?.issuer === record.customerSubject.issuer &&
        input.principal.subject === record.customerSubject.subject
      ) {
        return {
          accessMode: 'authenticated-subject',
          accessScope: {
            issuer: record.customerSubject.issuer,
            kind: 'authenticated_customer',
            profile: 'authenticated_customer',
            subject: record.customerSubject.subject,
          },
        };
      }
      throw new ConversationAccessDeniedError();
    }

    if (capabilityMatches(input.capability, record.capabilityHash)) {
      return {
        accessMode: 'anonymous-capability',
        accessScope: {
          capabilityHash: record.capabilityHash!,
          kind: 'public_capability',
          profile: 'public_customer',
        },
      };
    }
    throw new ConversationAccessDeniedError();
  }
}
