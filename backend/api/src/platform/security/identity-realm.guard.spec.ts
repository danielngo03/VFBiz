import type { ExecutionContext } from '@nestjs/common';
import { ForbiddenException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal } from './access-principal';
import { IdentityRealmGuard } from './identity-realm.guard';

function contextFor(
  request: Partial<FastifyRequest> & { vfbizPrincipal?: AccessPrincipal },
): ExecutionContext {
  return {
    getClass: () => class TestController {},
    getHandler: () => () => undefined,
    switchToHttp: () => ({
      getNext: () => undefined,
      getRequest: () => request,
      getResponse: () => undefined,
    }),
  } as unknown as ExecutionContext;
}

const principal = (realm: 'customer' | 'workforce'): AccessPrincipal => ({
  authenticationContext: null,
  authenticationMethods: [],
  audience: [`vfbiz-${realm}-api`],
  authorizedParty: `vfbiz-${realm}-bff`,
  issuer: `https://id.example/realms/${realm}`,
  realm,
  scopes: [],
  sessionId: null,
  subject: `${realm}-123`,
});

describe('IdentityRealmGuard', () => {
  it('allows routes without realm metadata', () => {
    const reflector = {
      getAllAndOverride: jest.fn().mockReturnValue(undefined),
    } as unknown as Reflector;
    const guard = new IdentityRealmGuard(reflector);

    expect(guard.canActivate(contextFor({ headers: {} }))).toBe(true);
  });

  it('allows only the required identity realm', () => {
    const reflector = {
      getAllAndOverride: jest.fn().mockReturnValue('customer'),
    } as unknown as Reflector;
    const guard = new IdentityRealmGuard(reflector);

    expect(
      guard.canActivate(
        contextFor({ headers: {}, vfbizPrincipal: principal('customer') }),
      ),
    ).toBe(true);
    expect(() =>
      guard.canActivate(
        contextFor({ headers: {}, vfbizPrincipal: principal('workforce') }),
      ),
    ).toThrow(ForbiddenException);
  });
});
