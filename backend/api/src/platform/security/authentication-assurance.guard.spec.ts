import { ForbiddenException, type ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { AccessPrincipal } from './access-principal';
import { AuthenticationAssuranceGuard } from './authentication-assurance.guard';

function contextFor(
  authenticationMethods: readonly string[],
): ExecutionContext {
  const principal: AccessPrincipal = {
    authenticationContext: null,
    authenticationMethods,
    audience: ['vfbiz-workforce-api'],
    authorizedParty: 'vfbiz-workforce-bff',
    issuer: 'https://id.example/realms/workforce',
    realm: 'workforce',
    roles: ['vehicle-data-operator'],
    scopes: [],
    sessionId: 'session-1',
    subject: 'operator-1',
  };
  return {
    getClass: () => class Controller {},
    getHandler: () => () => undefined,
    switchToHttp: () => ({
      getRequest: () => ({ vfbizPrincipal: principal }),
    }),
  } as unknown as ExecutionContext;
}

describe('AuthenticationAssuranceGuard', () => {
  const reflector = {
    getAllAndOverride: jest
      .fn()
      .mockReturnValue({ methods: ['otp'], mode: 'all-of' }),
  } as unknown as Reflector;

  it('allows a session that contains the required MFA method', () => {
    expect(
      new AuthenticationAssuranceGuard(reflector).canActivate(
        contextFor(['pwd', 'otp']),
      ),
    ).toBe(true);
  });

  it('fails closed when the MFA evidence is absent', () => {
    expect(() =>
      new AuthenticationAssuranceGuard(reflector).canActivate(
        contextFor(['pwd']),
      ),
    ).toThrow(ForbiddenException);
  });

  it('accepts either approved MFA method for an any-of policy', () => {
    const anyOfReflector = {
      getAllAndOverride: jest
        .fn()
        .mockReturnValue({ methods: ['otp', 'webauthn'], mode: 'any-of' }),
    } as unknown as Reflector;
    const guard = new AuthenticationAssuranceGuard(anyOfReflector);

    expect(guard.canActivate(contextFor(['pwd', 'otp']))).toBe(true);
    expect(guard.canActivate(contextFor(['pwd', 'webauthn']))).toBe(true);
  });
});
