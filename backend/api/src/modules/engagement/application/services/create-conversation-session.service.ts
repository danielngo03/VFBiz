import { createHash, randomBytes, randomUUID } from 'node:crypto';
import {
  ForbiddenException,
  HttpException,
  HttpStatus,
  Injectable,
  ServiceUnavailableException,
} from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { conversationSubjectKeyHash } from '../../domain/conversation-subject-key';
import { ActiveAssistantReleaseProjection } from '../ports/active-assistant-release-projection';
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
const INITIAL_MODEL_TOKEN_BUDGET = 50_000;
const INITIAL_COST_BUDGET_MICROS = 20_000_000;
const DAILY_MODEL_TOKEN_BUDGET = 100_000;
const DAILY_COST_BUDGET_MICROS = 20_000_000;

@Injectable()
export class CreateConversationSessionService {
  constructor(
    private readonly sessions: ConversationSessionRepository,
    private readonly releases: ActiveAssistantReleaseProjection,
  ) {}

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
    const subjectBudget =
      input.principal === null
        ? null
        : {
            subjectKeyHash: conversationSubjectKeyHash(
              input.principal.issuer,
              input.principal.subject,
            ),
            budgetDate: utcDayStart(now),
            dailyModelTokenLimit: DAILY_MODEL_TOKEN_BUDGET,
            dailyCostLimitMicros: DAILY_COST_BUDGET_MICROS,
            reserveModelTokens: INITIAL_MODEL_TOKEN_BUDGET,
            reserveCostMicros: INITIAL_COST_BUDGET_MICROS,
          };

    const release = await this.releases.resolve({
      now,
      profile: input.profile,
    });
    if (release === null) {
      throw new ServiceUnavailableException({
        code: 'ASSISTANT_RELEASE_UNAVAILABLE',
        message: 'No approved assistant release is active for this profile.',
      });
    }
    const capability =
      input.profile === 'public_customer'
        ? randomBytes(32).toString('base64url')
        : null;
    try {
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
        initialCostBudgetMicros: INITIAL_COST_BUDGET_MICROS,
        initialModelTokenBudget: INITIAL_MODEL_TOKEN_BUDGET,
        locale: input.locale,
        release,
        profile: input.profile,
        retentionUntil: new Date(now.getTime() + RETENTION_SECONDS * 1000),
        subjectBudget,
      });
      return {
        capability,
        expiresInSeconds: SESSION_TTL_SECONDS,
        session,
      };
    } catch (error) {
      if (
        error instanceof Error &&
        error.message === 'CUSTOMER_CHAT_DAILY_BUDGET_EXHAUSTED'
      ) {
        throw new HttpException(
          {
            code: 'CUSTOMER_CHAT_DAILY_BUDGET_EXHAUSTED',
            message: 'The daily customer chat budget has been exhausted.',
          },
          HttpStatus.TOO_MANY_REQUESTS,
        );
      }
      throw error;
    }
  }
}

function utcDayStart(value: Date): Date {
  return new Date(
    Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate()),
  );
}
