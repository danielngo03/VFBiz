import { ForbiddenException, type ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal } from './access-principal';
import { RoleAuthorizationGuard } from './role-authorization.guard';

function contextFor(principal?: AccessPrincipal): ExecutionContext {
  return {
    getClass: () => class TestController {},
    getHandler: () => () => undefined,
    switchToHttp: () => ({
      getRequest: () =>
        ({ vfbizPrincipal: principal }) as Partial<FastifyRequest> & {
          vfbizPrincipal?: AccessPrincipal;
        },
    }),
  } as unknown as ExecutionContext;
}

function principal(roles?: readonly string[]): AccessPrincipal {
  return {
    authenticationContext: 'urn:vfbiz:acr:mfa',
    authenticationMethods: ['pwd', 'otp'],
    audience: ['vfbiz-workforce-api'],
    authorizedParty: 'vfbiz-workforce-bff',
    issuer: 'https://id.example/realms/workforce',
    realm: 'workforce',
    roles,
    scopes: [],
    sessionId: 'session-1',
    subject: 'operator-1',
  };
}

describe('RoleAuthorizationGuard', () => {
  it('allows a principal with one accepted role', () => {
    const reflector = {
      getAllAndOverride: jest.fn().mockReturnValue({
        mode: 'any-of',
        roles: ['vehicle-data-reviewer', 'platform-admin'],
      }),
    } as unknown as Reflector;
    const guard = new RoleAuthorizationGuard(reflector);

    expect(
      guard.canActivate(contextFor(principal(['vehicle-data-reviewer']))),
    ).toBe(true);
  });

  it('fails closed when the role claim is absent', () => {
    const reflector = {
      getAllAndOverride: jest.fn().mockReturnValue({
        mode: 'all-of',
        roles: ['vehicle-data-operator'],
      }),
    } as unknown as Reflector;
    const guard = new RoleAuthorizationGuard(reflector);

    expect(() => guard.canActivate(contextFor(principal()))).toThrow(
      ForbiddenException,
    );
  });

  it('rejects insufficient roles', () => {
    const reflector = {
      getAllAndOverride: jest.fn().mockReturnValue({
        mode: 'all-of',
        roles: ['commercial-data-reviewer'],
      }),
    } as unknown as Reflector;
    const guard = new RoleAuthorizationGuard(reflector);

    expect(() =>
      guard.canActivate(contextFor(principal(['commercial-data-operator']))),
    ).toThrow(ForbiddenException);
  });
});
