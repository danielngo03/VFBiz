import { SetMetadata } from '@nestjs/common';

export const REQUIRED_ROLES = 'vfbiz.requiredRoles';

export type RoleRequirementMode = 'all-of' | 'any-of';

export interface RequiredRolesPolicy {
  readonly mode: RoleRequirementMode;
  readonly roles: readonly string[];
}

const ROLE_PATTERN = /^[a-z][a-z0-9-]{0,79}$/;

export function isRequiredRolesPolicy(
  value: unknown,
): value is RequiredRolesPolicy {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<RequiredRolesPolicy>;
  return (
    (candidate.mode === 'all-of' || candidate.mode === 'any-of') &&
    Array.isArray(candidate.roles) &&
    candidate.roles.length > 0 &&
    candidate.roles.every(
      (role) => typeof role === 'string' && ROLE_PATTERN.test(role),
    )
  );
}

export function RequireRoles(policy: RequiredRolesPolicy) {
  if (!isRequiredRolesPolicy(policy)) {
    throw new TypeError(
      'Required roles must use all-of or any-of with concrete role names.',
    );
  }
  return SetMetadata(
    REQUIRED_ROLES,
    Object.freeze({
      mode: policy.mode,
      roles: Object.freeze([...new Set(policy.roles)]),
    }),
  );
}
