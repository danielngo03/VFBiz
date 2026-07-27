import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';
import type { ConversationTurnExecutionContext } from './conversation-runtime.repository';

export type ConversationAiTransportFailureCode =
  | 'cancelled'
  | 'circuit_open'
  | 'invalid_response'
  | 'policy_denied'
  | 'provider_unavailable'
  | 'stale_execution'
  | 'timeout';

export class ConversationAiTransportError extends Error {
  constructor(
    readonly code: ConversationAiTransportFailureCode,
    readonly retryable: boolean,
  ) {
    super(`Internal AI transport failed with ${code}.`);
    this.name = 'ConversationAiTransportError';
  }
}

export interface ConversationAiExecutionRequest extends ConversationTurnExecutionContext {
  readonly correlationId: string;
  readonly deadlineAt: Date;
  readonly requestId: string;
}

export interface ConversationAiCancellationRequest {
  readonly accessScope: ConversationAccessScope;
  readonly assistantProfile: 'authenticated_customer' | 'public_customer';
  readonly budget: {
    readonly maxCostMicros: number;
    readonly maxModelTokens: number;
  };
  readonly conversationVersion: number;
  readonly correlationId: string;
  readonly fencingToken: number;
  readonly locale: 'en' | 'vi';
  readonly release: ConversationTurnExecutionContext['release'];
  readonly policyRevision: string;
  readonly reason:
    'budget_exhausted' | 'system_shutdown' | 'timeout' | 'user_interrupt';
  readonly requestId: string;
  readonly sessionId: string;
  readonly turnId: string;
}

export interface ConversationAiUsage {
  readonly costMicros: number;
  readonly modelTokens: number;
}

export interface ConversationAiReleaseCommitReceipt {
  readonly activationEnvelopeSha256: string;
  readonly activationId: string;
  readonly candidateSha256: string;
  readonly conversationVersion: number;
  readonly expiresAt: Date;
  readonly fencingToken: number;
  readonly issuedAt: Date;
  readonly leaseId: string;
  readonly pointerRevision: number;
  readonly requestId: string;
  readonly sessionId: string;
  readonly turnId: string;
}

interface ConversationAiResultBase {
  readonly releaseCommitReceipt: ConversationAiReleaseCommitReceipt | null;
  readonly releaseRevision: string;
  readonly revisions: {
    readonly graph: string;
    readonly knowledge: string;
    readonly policy: string;
  };
  readonly usage: ConversationAiUsage;
}

export type ConversationAiExecutionResult =
  | (ConversationAiResultBase & {
      readonly citations: readonly {
        readonly retrievedAt: Date;
        readonly revision: string;
        readonly sourceId: string;
        readonly title: string;
        readonly uri: string;
      }[];
      readonly message: string;
      readonly outcome: 'answered';
    })
  | (ConversationAiResultBase & {
      readonly code: 'RELEASE_SUPPRESSED';
      readonly message: string;
      readonly outcome: 'failed_safely';
    })
  | (ConversationAiResultBase & {
      readonly message: string;
      readonly outcome: 'conversational' | 'refused';
    })
  | (ConversationAiResultBase & {
      readonly message: string;
      readonly outcome: 'clarification_required';
      readonly pendingSlots: readonly string[];
    })
  | (ConversationAiResultBase & {
      readonly customerMessage: string;
      readonly outcome: 'handoff_recommended';
      readonly reason:
        | 'insufficient_evidence'
        | 'policy_required'
        | 'safety_risk'
        | 'tool_unavailable';
    })
  | (ConversationAiResultBase & {
      readonly arguments: Readonly<Record<string, unknown>>;
      readonly argumentsHash: string;
      readonly outcome: 'tool_proposal';
      readonly schemaVersion: string;
      readonly tool:
        | 'get_customer_garage'
        | 'get_vehicle_profile'
        | 'list_charging_stations'
        | 'search_public_knowledge';
    });

export interface ConversationAiCancellationResult {
  readonly status: 'accepted' | 'already_terminal';
}

export abstract class ConversationAiTransport {
  abstract cancel(
    request: ConversationAiCancellationRequest,
    signal?: AbortSignal,
  ): Promise<ConversationAiCancellationResult>;

  abstract execute(
    request: ConversationAiExecutionRequest,
    signal?: AbortSignal,
  ): Promise<ConversationAiExecutionResult>;
}
