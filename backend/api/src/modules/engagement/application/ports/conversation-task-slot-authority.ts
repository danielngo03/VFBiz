import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';
import type { ConfirmedConversationContextEntity } from '../../domain/runtime/conversation-runtime';
import type {
  ConversationTaskReleaseBinding,
  ConversationTaskSlotReference,
} from '../../domain/runtime/conversation-task-context';

export interface ConversationTaskSlotCandidate {
  readonly candidateId: string;
  readonly confidence: number;
  readonly expectedTaskVersion: number;
  readonly kind: 'candidate';
  readonly proposedValue: string;
  readonly provenanceDigest: string;
  readonly slot: string;
  readonly sourceTurnId: string;
  readonly taskId: string;
}

export interface ConversationTaskProposal {
  readonly authorizationContextDigest: string;
  readonly expectedTaskVersion: number;
  readonly expiresAt: Date;
  readonly intent: string;
  readonly intentRevision: string;
  readonly pendingSlots: readonly string[];
  readonly provenanceDigest: string;
  readonly release: ConversationTaskReleaseBinding;
  readonly slotCandidates: readonly ConversationTaskSlotCandidate[];
  readonly sourceTurnId: string;
  readonly taskId: string;
}

export type ConversationTaskSlotResolution =
  | {
      readonly kind: 'resolved';
      readonly receipt: ConversationTaskSlotReference;
      readonly slot: string;
      readonly taskId: string;
    }
  | {
      readonly kind: 'unresolved';
      readonly reason: 'ambiguous' | 'not_found' | 'unsupported_slot';
    }
  | {
      readonly kind: 'rejected';
      readonly reason: 'anomaly' | 'stale_source' | 'unauthorized';
    }
  | {
      readonly kind: 'failed_safely';
      readonly reason: 'authority_timeout' | 'authority_unavailable';
    };

export abstract class ConversationTaskSlotAuthority {
  abstract resolve(input: {
    accessScope: ConversationAccessScope;
    assistantProfile: 'authenticated_customer' | 'public_customer';
    candidate: ConversationTaskSlotCandidate;
    confirmedEntities: readonly ConfirmedConversationContextEntity[];
    intent: string;
    release: ConversationTaskReleaseBinding;
    signal?: AbortSignal;
  }): Promise<ConversationTaskSlotResolution>;
}
