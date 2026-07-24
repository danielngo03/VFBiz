import { SetMetadata } from '@nestjs/common';

export const REQUIRED_CAPABILITIES = 'vfbiz.requiredCapabilities';

export type CapabilityRequirementMode = 'all-of' | 'any-of';

export interface RequiredCapabilitiesPolicy {
  readonly mode: CapabilityRequirementMode;
  readonly capabilities: readonly string[];
}

const CAPABILITY_PATTERN = /^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*){2,3}$/;

export function isRequiredCapabilitiesPolicy(
  value: unknown,
): value is RequiredCapabilitiesPolicy {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<RequiredCapabilitiesPolicy>;
  return (
    (candidate.mode === 'all-of' || candidate.mode === 'any-of') &&
    Array.isArray(candidate.capabilities) &&
    candidate.capabilities.length > 0 &&
    candidate.capabilities.every(
      (capability) =>
        typeof capability === 'string' && CAPABILITY_PATTERN.test(capability),
    )
  );
}

export function RequireCapabilities(policy: RequiredCapabilitiesPolicy) {
  if (!isRequiredCapabilitiesPolicy(policy)) {
    throw new TypeError(
      'Required capabilities must use all-of or any-of with concrete capability keys.',
    );
  }
  return SetMetadata(
    REQUIRED_CAPABILITIES,
    Object.freeze({
      mode: policy.mode,
      capabilities: Object.freeze([...new Set(policy.capabilities)]),
    }),
  );
}
