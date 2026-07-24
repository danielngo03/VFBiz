import 'server-only';

export type OpaqueSessionId = string & {readonly __opaqueSessionId: unique symbol};

export interface WorkforceBffSession {
  readonly authenticatedAt: Date;
  readonly deviceLabel: string | null;
  readonly emailVerified: boolean;
  readonly id: OpaqueSessionId;
  readonly subject: string;
  readonly mfaSatisfied: boolean;
  readonly entitlementRevision: string;
  readonly expiresAt: Date;
  readonly lastSeenAt: Date;
  readonly networkHint: string | null;
  readonly userAgentSummary: string | null;
}

export interface WorkforceTokenSet {
  readonly accessToken: string;
  readonly refreshToken?: string;
  readonly expiresAt: Date;
}
