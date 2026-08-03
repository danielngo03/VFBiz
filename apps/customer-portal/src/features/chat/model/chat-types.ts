export type ConversationStatus = "active" | "handoff" | "closed";

export interface ConversationSession {
  readonly id: string;
  readonly profile: "authenticated_customer" | "public_customer";
  readonly locale: "vi" | "en";
  readonly status: ConversationStatus;
  readonly version: number;
  readonly createdAt: string;
  readonly expiresAt: string;
  readonly retentionUntil: string;
}

export interface Citation {
  readonly sourceId: string;
  readonly title: string;
  readonly uri?: string;
  readonly revision: string;
  readonly retrievedAt: string;
}

export interface ConversationMessage {
  readonly id: string;
  readonly role: "customer" | "assistant";
  readonly sequence: number;
  readonly content: string;
  readonly outcome: "answered" | "conversational" | "refused" | "handed_off" | null;
  readonly citations: readonly Citation[];
  readonly createdAt: string;
}

export interface ConversationMessagePage {
  readonly items: readonly ConversationMessage[];
  readonly nextCursor: string | null;
}

export interface MessageAccepted {
  readonly kind: "message.accepted";
  readonly turnId: string;
  readonly conversationVersion: number;
  readonly eventCursor: string;
}

export interface ConversationEvent {
  readonly eventId?: string;
  readonly turnId: string;
  readonly type: string;
  readonly data: unknown;
}
