import type { AccessPrincipal } from '../../../platform/security/access-principal';

export const WORKFORCE_SCOPE_TYPES = [
  'global',
  'market',
  'showroom',
  'department',
] as const;
export type WorkforceScopeType = (typeof WORKFORCE_SCOPE_TYPES)[number];

export const CAPABILITY_RISK_TIERS = [
  'standard',
  'sensitive',
  'privileged',
] as const;
export type CapabilityRiskTier = (typeof CAPABILITY_RISK_TIERS)[number];

export interface CapabilityDefinition {
  readonly key: string;
  readonly resource: string;
  readonly action: string;
  readonly riskTier: CapabilityRiskTier;
  readonly displayName: string;
  readonly deprecated: boolean;
  readonly catalogVersion: number;
}

export interface AuthorizationScope {
  readonly type: WorkforceScopeType;
  readonly ref: string;
}

export interface WorkforceEntitlements {
  readonly identitySubjectId: string;
  readonly revision: string;
  readonly capabilities: ReadonlyArray<{
    readonly key: string;
    readonly riskTier: CapabilityRiskTier;
    readonly scopes: readonly AuthorizationScope[];
  }>;
}

export interface AuthorizationDecision {
  readonly allowed: boolean;
  readonly code:
    | 'ALLOWED'
    | 'IDENTITY_NOT_REGISTERED'
    | 'INSUFFICIENT_CAPABILITY'
    | 'STEP_UP_AUTHENTICATION_REQUIRED';
  readonly revision: string | null;
}

export interface WorkforceRoleView {
  readonly id: string;
  readonly key: string;
  readonly displayName: string;
  readonly description: string | null;
  readonly status: 'active' | 'disabled';
  readonly system: boolean;
  readonly version: number;
  readonly capabilityKeys: readonly string[];
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export interface WorkforceAssignmentView {
  readonly id: string;
  readonly identitySubjectId: string;
  readonly roleId: string;
  readonly roleKey: string;
  readonly status: 'active' | 'revoked';
  readonly effectiveAt: Date;
  readonly expiresAt: Date | null;
  readonly reason: string;
  readonly version: number;
  readonly scopes: readonly AuthorizationScope[];
}

export interface AuthorizationChangeRequestView {
  readonly id: string;
  readonly requestType: string;
  readonly status: 'pending' | 'approved' | 'rejected';
  readonly riskTier: CapabilityRiskTier;
  readonly requesterRef: string;
  readonly targetType: string;
  readonly targetRef: string;
  readonly reason: string;
  readonly payload: unknown;
  readonly expiresAt: Date;
  readonly decidedAt: Date | null;
}

export interface WorkforceDirectorySubjectView {
  readonly id: string;
  readonly externalSubject: string;
  readonly status: string;
}

export interface WorkforceOrganizationUnitView {
  readonly id: string;
  readonly externalRef: string;
  readonly type: WorkforceScopeType;
  readonly displayName: string;
  readonly status: string;
  readonly source: string;
  readonly revision: string;
  readonly observedAt: Date;
}

export interface WorkforceAuditEventView {
  readonly id: string;
  readonly actorRef: string | null;
  readonly action: string;
  readonly resourceType: string;
  readonly resourceId: string | null;
  readonly outcome: string;
  readonly correlationId: string;
  readonly occurredAt: Date;
}

export function principalReference(principal: AccessPrincipal): string {
  return `${principal.issuer}|${principal.subject}`;
}

export function isScopeValid(scope: {
  readonly type: string;
  readonly ref: string;
}): scope is AuthorizationScope {
  if (!WORKFORCE_SCOPE_TYPES.some((type) => type === scope.type)) {
    return false;
  }
  if (scope.type === 'global') return scope.ref === 'global';
  return scope.ref.length > 0 && scope.ref !== 'global';
}

export function scopeAllows(
  grantedScopes: readonly AuthorizationScope[],
  requestedScope?: AuthorizationScope,
): boolean {
  if (grantedScopes.some((scope) => scope.type === 'global')) return true;
  if (requestedScope === undefined) return false;
  return grantedScopes.some(
    (scope) =>
      scope.type === requestedScope.type && scope.ref === requestedScope.ref,
  );
}
