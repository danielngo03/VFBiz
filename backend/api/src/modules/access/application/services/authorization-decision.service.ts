import { Injectable } from '@nestjs/common';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import type { RequiredCapabilitiesPolicy } from '../../../../platform/security/required-capabilities';
import { WorkforceAuthorizationRepository } from '../ports/workforce-authorization.repository';
import {
  scopeAllows,
  type AuthorizationDecision,
  type AuthorizationScope,
  type WorkforceEntitlements,
} from '../../domain/workforce-authorization';
import { WorkforceEntitlementReader } from '../../../../platform/security/workforce-entitlement-reader';

const PRIVILEGED_MFA_MAX_AGE_MS = 5 * 60 * 1000;

function hasRecentMfa(principal: AccessPrincipal, now: Date): boolean {
  if (
    !principal.authenticationMethods.some((method) =>
      ['otp', 'mfa', 'webauthn'].includes(method),
    )
  ) {
    return false;
  }
  if (!('authenticatedAt' in principal)) return false;
  const authenticatedAt = principal.authenticatedAt;
  return (
    authenticatedAt instanceof Date &&
    authenticatedAt.getTime() <= now.getTime() + 60_000 &&
    now.getTime() - authenticatedAt.getTime() <= PRIVILEGED_MFA_MAX_AGE_MS
  );
}

@Injectable()
export class AuthorizationDecisionService extends WorkforceEntitlementReader {
  constructor(private readonly repository: WorkforceAuthorizationRepository) {
    super();
  }

  getEntitlements(
    principal: AccessPrincipal,
    now = new Date(),
  ): Promise<WorkforceEntitlements | null> {
    if (principal.realm !== 'workforce') return Promise.resolve(null);
    return this.repository.resolveEntitlements(principal, now);
  }

  async decide(
    principal: AccessPrincipal,
    policy: RequiredCapabilitiesPolicy,
    requestedScope?: AuthorizationScope,
    now = new Date(),
  ): Promise<AuthorizationDecision> {
    const entitlements = await this.getEntitlements(principal, now);
    if (entitlements === null) {
      return {
        allowed: false,
        code: 'IDENTITY_NOT_REGISTERED',
        revision: null,
      };
    }

    const grants = new Map(
      entitlements.capabilities.map((grant) => [grant.key, grant]),
    );
    const matches = policy.capabilities.map((key) => {
      const grant = grants.get(key);
      return grant !== undefined && scopeAllows(grant.scopes, requestedScope);
    });
    const allowed =
      policy.mode === 'all-of' ? matches.every(Boolean) : matches.some(Boolean);
    if (!allowed) {
      return {
        allowed: false,
        code: 'INSUFFICIENT_CAPABILITY',
        revision: entitlements.revision,
      };
    }

    const privileged = policy.capabilities.some(
      (key) => grants.get(key)?.riskTier === 'privileged',
    );
    if (privileged && !hasRecentMfa(principal, now)) {
      return {
        allowed: false,
        code: 'STEP_UP_AUTHENTICATION_REQUIRED',
        revision: entitlements.revision,
      };
    }

    return {
      allowed: true,
      code: 'ALLOWED',
      revision: entitlements.revision,
    };
  }
}
