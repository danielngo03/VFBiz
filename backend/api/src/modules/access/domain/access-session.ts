export type AccessSessionStatus = 'active' | 'expired' | 'revoked';

export type SessionRevocationReconciliation =
  'confirmed' | 'manual_review_required' | 'pending' | 'retry_required';

export type SessionRevocationState =
  | 'none'
  | 'pending'
  | 'confirmed'
  | 'manual_review_required'
  | 'retry_required';

export interface AccessSessionView {
  readonly authenticatedAt: Date;
  readonly deviceLabel: string | null;
  readonly emailVerified: boolean | null;
  readonly expiresAt: Date;
  readonly id: string;
  readonly isCurrent: boolean;
  readonly mfaSatisfied: boolean;
  readonly networkHint: string | null;
  readonly lastSeenAt: Date;
  readonly revokedAt: Date | null;
  readonly status: AccessSessionStatus;
  readonly userAgentSummary: string | null;
}

export interface SessionClientContext {
  readonly deviceLabel: string | null;
  readonly ipPrefix: string | null;
  readonly userAgentSummary: string | null;
}

export interface ReconcileSessionObservation {
  readonly authenticatedAt: Date;
  readonly authorizedParty: string;
  readonly deviceLabel: string | null;
  readonly emailVerified: boolean | null;
  readonly expiresAt: Date;
  readonly issuer: string;
  readonly ipPrefix: string | null;
  readonly lastSeenAt: Date;
  readonly mfaSatisfied: boolean;
  readonly eventRevision: bigint;
  readonly observedAt: Date;
  readonly providerRoute: 'customer-ciam';
  readonly providerSessionSecretReference: string | null;
  readonly realm: 'customer';
  readonly revokedAt: Date | null;
  readonly sessionReference: string;
  readonly subject: string;
  readonly userAgentSummary: string | null;
}

export interface RevokeSessionView {
  readonly reconciliation: SessionRevocationReconciliation;
  readonly session: AccessSessionView;
}

export interface RevokeAllSessionsView {
  readonly locallyRevokedCount: number;
  readonly reconciliation: SessionRevocationReconciliation;
}

export interface CustomerIdentitySecurityView {
  readonly currentSessionMfaSatisfied: boolean;
  readonly emailVerified: boolean | null;
  readonly mfaConfigured: boolean | null;
  readonly providerStatus: 'available' | 'unavailable';
}

export class AccessSessionNotFoundError extends Error {
  constructor() {
    super('The access session was not found.');
    this.name = 'AccessSessionNotFoundError';
  }
}

export class InvalidSessionObservationError extends Error {
  constructor() {
    super('The session observation is invalid.');
    this.name = 'InvalidSessionObservationError';
  }
}

export class MissingSessionReferenceError extends Error {
  constructor() {
    super('The verified customer token does not contain a session reference.');
    this.name = 'MissingSessionReferenceError';
  }
}

export function sessionStatus(
  revokedAt: Date | null,
  expiresAt: Date,
  now: Date,
): AccessSessionStatus {
  if (revokedAt !== null) return 'revoked';
  if (expiresAt.getTime() <= now.getTime()) return 'expired';
  return 'active';
}

export function assertValidObservation(
  observation: ReconcileSessionObservation,
  now = new Date(),
): void {
  const maximumClockSkewMs = 5 * 60 * 1000;
  const timestamps = [
    observation.authenticatedAt,
    observation.lastSeenAt,
    observation.expiresAt,
    observation.observedAt,
    ...(observation.revokedAt === null ? [] : [observation.revokedAt]),
  ];
  if (
    timestamps.some((value) => Number.isNaN(value.getTime())) ||
    observation.authenticatedAt.getTime() > observation.lastSeenAt.getTime() ||
    observation.authenticatedAt.getTime() >= observation.expiresAt.getTime() ||
    observation.lastSeenAt.getTime() >= observation.expiresAt.getTime() ||
    observation.sessionReference.length === 0 ||
    observation.issuer.length === 0 ||
    observation.subject.length === 0 ||
    observation.authorizedParty.length === 0 ||
    observation.eventRevision <= 0n ||
    observation.observedAt.getTime() > now.getTime() + maximumClockSkewMs ||
    observation.lastSeenAt.getTime() >
      observation.observedAt.getTime() + maximumClockSkewMs ||
    (observation.revokedAt !== null &&
      observation.revokedAt.getTime() <
        observation.authenticatedAt.getTime()) ||
    (observation.revokedAt !== null &&
      observation.revokedAt.getTime() >
        observation.observedAt.getTime() + maximumClockSkewMs) ||
    observation.providerRoute !== 'customer-ciam' ||
    (observation.providerSessionSecretReference !== null &&
      !/^secret:\/\/[A-Za-z0-9/_:.-]{1,503}$/.test(
        observation.providerSessionSecretReference,
      )) ||
    (observation.deviceLabel?.length ?? 0) > 120 ||
    (observation.userAgentSummary?.length ?? 0) > 255 ||
    (observation.ipPrefix?.length ?? 0) > 80
  ) {
    throw new InvalidSessionObservationError();
  }
}
