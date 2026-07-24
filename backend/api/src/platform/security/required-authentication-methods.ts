import { SetMetadata } from '@nestjs/common';

export const REQUIRED_AUTHENTICATION_METHODS =
  'vfbiz.requiredAuthenticationMethods';

export interface RequiredAuthenticationMethodsPolicy {
  readonly methods: readonly string[];
  readonly mode: 'all-of' | 'any-of';
}

function policy(
  methods: readonly [string, ...string[]],
  mode: RequiredAuthenticationMethodsPolicy['mode'],
): RequiredAuthenticationMethodsPolicy {
  const unique = [...new Set(methods)];
  if (
    unique.length === 0 ||
    !unique.every((method) => /^[a-z0-9:_-]{1,80}$/i.test(method))
  ) {
    throw new TypeError('Authentication methods must be concrete names.');
  }
  return Object.freeze({ methods: Object.freeze(unique), mode });
}

export function RequireAuthenticationMethods(
  methods: readonly [string, ...string[]],
) {
  return SetMetadata(
    REQUIRED_AUTHENTICATION_METHODS,
    policy(methods, 'all-of'),
  );
}

export function RequireAnyAuthenticationMethod(
  methods: readonly [string, ...string[]],
) {
  return SetMetadata(
    REQUIRED_AUTHENTICATION_METHODS,
    policy(methods, 'any-of'),
  );
}
