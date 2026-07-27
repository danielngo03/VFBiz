export interface ConversationCustomerSubject {
  readonly issuer: string;
  readonly subject: string;
}

export interface ConversationAccessRecord {
  readonly capabilityHash: string | null;
  readonly customerSubject: ConversationCustomerSubject | null;
  readonly expiresAt: Date;
  readonly id: string;
  readonly status: string;
}

export interface ConversationMessageView {
  readonly citations: readonly {
    readonly retrievedAt: Date;
    readonly revision: string;
    readonly sourceId: string;
    readonly title: string;
    readonly uri: string;
  }[];
  readonly content: string;
  readonly createdAt: Date;
  readonly id: string;
  readonly outcome: string | null;
  readonly role: string;
}

export interface CreateConversationSessionRecordInput {
  readonly capabilityHash: string | null;
  readonly customerSubject: ConversationCustomerSubject | null;
  readonly expiresAt: Date;
  readonly id: string;
  readonly initialCostBudgetMicros: number;
  readonly initialModelTokenBudget: number;
  readonly locale: 'vi' | 'en';
  readonly release: import('./active-assistant-release-projection').AssistantReleaseBinding;
  readonly profile: 'public_customer' | 'authenticated_customer';
  readonly retentionUntil: Date;
}

export interface CreatedConversationSessionRecord {
  readonly createdAt: Date;
  readonly id: string;
  readonly locale: 'vi' | 'en';
  readonly profile: 'public_customer' | 'authenticated_customer';
}

export interface ConversationSessionSummary {
  readonly createdAt: Date;
  readonly expiresAt: Date;
  readonly id: string;
  readonly locale: 'vi' | 'en';
  readonly profile: 'public_customer' | 'authenticated_customer';
  readonly retentionUntil: Date;
}

export abstract class ConversationSessionRepository {
  abstract createSession(
    input: CreateConversationSessionRecordInput,
  ): Promise<CreatedConversationSessionRecord>;

  abstract findAccessRecord(
    sessionId: string,
  ): Promise<ConversationAccessRecord | null>;

  abstract findSessionSummary(
    sessionId: string,
  ): Promise<ConversationSessionSummary | null>;

  abstract listMessages(
    sessionId: string,
    accessScope: ConversationAccessScope,
  ): Promise<readonly ConversationMessageView[]>;
}
import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';
