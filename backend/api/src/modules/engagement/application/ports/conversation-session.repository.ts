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
  readonly locale: 'vi' | 'en';
  readonly policyRevision: string;
  readonly profile: 'public_customer' | 'authenticated_customer';
  readonly retentionUntil: Date;
}

export interface CreatedConversationSessionRecord {
  readonly createdAt: Date;
  readonly id: string;
  readonly locale: 'vi' | 'en';
  readonly profile: 'public_customer' | 'authenticated_customer';
}

export abstract class ConversationSessionRepository {
  abstract createSession(
    input: CreateConversationSessionRecordInput,
  ): Promise<CreatedConversationSessionRecord>;

  abstract findAccessRecord(
    sessionId: string,
  ): Promise<ConversationAccessRecord | null>;

  abstract listMessages(
    sessionId: string,
  ): Promise<readonly ConversationMessageView[]>;
}
