import "server-only";

export type OpaqueCustomerSessionId = string & {
  readonly __opaqueCustomerSessionId: unique symbol;
};

export interface CustomerBffSession {
  readonly authenticatedAt: Date;
  readonly csrfToken: string;
  readonly deviceLabel: string | null;
  readonly emailVerified: true;
  readonly expiresAt: Date;
  readonly id: OpaqueCustomerSessionId;
  readonly lastSeenAt: Date;
  readonly mfaSatisfied: boolean;
  readonly networkHint: string | null;
  readonly providerSessionId: string;
  readonly subject: string;
  readonly userAgentSummary: string | null;
}

export interface CustomerTokenSet {
  readonly accessToken: string;
  readonly expiresAt: Date;
  readonly refreshToken?: string;
}

export type ProviderRevocationReconciliation =
  "confirmed" | "pending" | "retry_required";
