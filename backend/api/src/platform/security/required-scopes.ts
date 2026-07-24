import { SetMetadata } from '@nestjs/common';

export const REQUIRED_SCOPES = 'vfbiz.requiredScopes';

export type ScopeRequirementMode = 'all-of' | 'any-of';

export interface RequiredScopesDeclaration {
  readonly allowedAuthorizedParties: readonly [string, ...string[]];
  readonly mode: ScopeRequirementMode;
  readonly scopes: readonly [string, ...string[]];
}

export interface RequiredScopesPolicy {
  readonly allowedAuthorizedParties: readonly string[];
  readonly mode: ScopeRequirementMode;
  readonly scopes: readonly string[];
}

export function isRfc6749ScopeToken(value: unknown): value is string {
  if (typeof value !== 'string' || value.length === 0) return false;

  for (const character of value) {
    const codePoint = character.codePointAt(0);
    if (
      codePoint === undefined ||
      !(
        codePoint === 0x21 ||
        (codePoint >= 0x23 && codePoint <= 0x5b) ||
        (codePoint >= 0x5d && codePoint <= 0x7e)
      )
    ) {
      return false;
    }
  }
  return true;
}

export function isConcreteAuthorizedParty(value: unknown): value is string {
  return (
    isRfc6749ScopeToken(value) && value.length <= 200 && !value.includes('*')
  );
}

export function isRequiredScopesPolicy(
  value: unknown,
): value is RequiredScopesPolicy {
  if (typeof value !== 'object' || value === null) return false;

  const candidate = value as Partial<RequiredScopesPolicy>;
  return (
    (candidate.mode === 'all-of' || candidate.mode === 'any-of') &&
    Array.isArray(candidate.allowedAuthorizedParties) &&
    candidate.allowedAuthorizedParties.length > 0 &&
    candidate.allowedAuthorizedParties.every(isConcreteAuthorizedParty) &&
    Array.isArray(candidate.scopes) &&
    candidate.scopes.length > 0 &&
    candidate.scopes.every(
      (scope) => isRfc6749ScopeToken(scope) && !scope.includes('*'),
    )
  );
}

export function RequireScopes(declaration: RequiredScopesDeclaration) {
  if (declaration.mode !== 'all-of' && declaration.mode !== 'any-of') {
    throw new TypeError('Scope matching mode must be all-of or any-of.');
  }
  if (declaration.scopes.length === 0) {
    throw new TypeError('At least one required scope must be declared.');
  }
  if (declaration.allowedAuthorizedParties.length === 0) {
    throw new TypeError('At least one authorized party must be declared.');
  }

  const uniqueScopes = [...new Set(declaration.scopes)];
  if (
    !uniqueScopes.every(
      (scope) => isRfc6749ScopeToken(scope) && !scope.includes('*'),
    )
  ) {
    throw new TypeError(
      'Required scopes must be concrete RFC 6749 scope tokens.',
    );
  }
  const uniqueAuthorizedParties = [
    ...new Set(declaration.allowedAuthorizedParties),
  ];
  if (!uniqueAuthorizedParties.every(isConcreteAuthorizedParty)) {
    throw new TypeError(
      'Authorized parties must be concrete non-empty client identifiers.',
    );
  }

  const policy: RequiredScopesPolicy = Object.freeze({
    allowedAuthorizedParties: Object.freeze(uniqueAuthorizedParties),
    mode: declaration.mode,
    scopes: Object.freeze(uniqueScopes),
  });
  return SetMetadata(REQUIRED_SCOPES, policy);
}
