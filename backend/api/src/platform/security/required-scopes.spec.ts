import 'reflect-metadata';
import {
  REQUIRED_SCOPES,
  RequireScopes,
  type RequiredScopesPolicy,
} from './required-scopes';

describe('RequireScopes', () => {
  it('publishes an immutable, de-duplicated all-of policy', () => {
    class TestController {}

    RequireScopes({
      allowedAuthorizedParties: ['vfbiz-customer-bff', 'vfbiz-customer-bff'],
      mode: 'all-of',
      scopes: ['chat:read', 'chat:write', 'chat:read'],
    })(TestController);

    const policy = Reflect.getMetadata(
      REQUIRED_SCOPES,
      TestController,
    ) as RequiredScopesPolicy;
    expect(policy).toEqual({
      allowedAuthorizedParties: ['vfbiz-customer-bff'],
      mode: 'all-of',
      scopes: ['chat:read', 'chat:write'],
    });
    expect(Object.isFrozen(policy)).toBe(true);
    expect(Object.isFrozen(policy.allowedAuthorizedParties)).toBe(true);
    expect(Object.isFrozen(policy.scopes)).toBe(true);
  });

  it('requires valid semantics, scopes and authorized parties', () => {
    const unsafeFactory = RequireScopes as unknown as (
      declaration: Record<string, unknown>,
    ) => ClassDecorator;

    expect(() =>
      unsafeFactory({
        allowedAuthorizedParties: ['vfbiz-customer-bff'],
        mode: 'all-of',
        scopes: [],
      }),
    ).toThrow('At least one required scope must be declared.');
    expect(() =>
      unsafeFactory({
        allowedAuthorizedParties: ['vfbiz-customer-bff'],
        mode: 'some-of',
        scopes: ['chat:read'],
      }),
    ).toThrow('Scope matching mode must be all-of or any-of.');
    expect(() =>
      unsafeFactory({
        allowedAuthorizedParties: ['vfbiz-customer-bff'],
        mode: 'any-of',
        scopes: ['chat:*'],
      }),
    ).toThrow('Required scopes must be concrete RFC 6749 scope tokens.');
    expect(() =>
      unsafeFactory({
        allowedAuthorizedParties: [],
        mode: 'any-of',
        scopes: ['chat:read'],
      }),
    ).toThrow('At least one authorized party must be declared.');
    expect(() =>
      unsafeFactory({
        allowedAuthorizedParties: ['*'],
        mode: 'any-of',
        scopes: ['chat:read'],
      }),
    ).toThrow(
      'Authorized parties must be concrete non-empty client identifiers.',
    );
  });
});
