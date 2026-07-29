export type InternalAiExecutionAction = 'turn.cancel' | 'turn.execute';
export type InternalAiAssistantProfile =
  'authenticated_customer' | 'public_customer';
export type InternalAiLocale = 'en' | 'vi';

export type InternalAiReadOnlyTool =
  | 'get_customer_garage'
  | 'get_vehicle_profile'
  | 'list_charging_stations'
  | 'search_public_knowledge';

export interface InternalAiPublicAuthorization {
  readonly allowedTools: readonly 'search_public_knowledge'[];
  readonly capabilityHash: string;
  readonly kind: 'public_capability';
}

export interface InternalAiCustomerAuthorization {
  readonly allowedTools: readonly InternalAiReadOnlyTool[];
  readonly kind: 'authenticated_customer';
  readonly scopes: readonly string[];
  readonly subjectRef: string;
}

export type InternalAiAuthorization =
  InternalAiCustomerAuthorization | InternalAiPublicAuthorization;

export interface InternalAiTurnBudget {
  readonly deadlineAt: string;
  readonly maxCostMicros: number;
  readonly maxModelTokens: number;
}

export interface InternalAiExecutionAssertionInput {
  readonly action: InternalAiExecutionAction;
  readonly assistantProfile: InternalAiAssistantProfile;
  readonly authorizationContextDigest: string;
  readonly authorization: InternalAiAuthorization;
  readonly budget: InternalAiTurnBudget;
  readonly conversationVersion: number;
  readonly correlationId: string;
  readonly fencingToken: number;
  readonly locale: InternalAiLocale;
  readonly graphRevision: string;
  readonly knowledgeRevision: string;
  readonly manifestSha256: string;
  readonly activationId: string;
  readonly policyRevision: string;
  readonly requestHash: string;
  readonly requestId: string;
  readonly sessionId: string;
  readonly turnId: string;
}

export interface InternalAiExecutionAssertionClaims extends InternalAiExecutionAssertionInput {
  readonly aud: 'vfbiz-ai';
  readonly exp: number;
  readonly iat: number;
  readonly iss: 'vfbiz-api';
  readonly jti: string;
  readonly nbf: number;
  readonly policyRevision: string;
}
