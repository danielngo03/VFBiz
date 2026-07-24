import { ForbiddenException } from '@nestjs/common';
import type { ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { AuthorizationDecisionService } from '../application/services/authorization-decision.service';
import { CapabilityAuthorizationGuard } from './capability-authorization.guard';

function context(principal?: AccessPrincipal): ExecutionContext {
  return {
    getClass: () => class TestController {},
    getHandler: () => () => undefined,
    switchToHttp: () => ({
      getRequest: () => ({ vfbizPrincipal: principal }),
    }),
  } as unknown as ExecutionContext;
}

const workforcePrincipal: AccessPrincipal = {
  audience: ['vfbiz-api'],
  authenticationContext: null,
  authenticationMethods: ['otp'],
  authorizedParty: 'vfbiz-workforce-portal',
  issuer: 'https://identity.example/realms/vfbiz-workforce',
  realm: 'workforce',
  scopes: ['openid'],
  sessionId: 'session-1',
  subject: 'worker-1',
};

describe('CapabilityAuthorizationGuard', () => {
  it('does nothing when the route has no capability requirement', async () => {
    const reflector = {
      getAllAndOverride: jest.fn().mockReturnValue(undefined),
    } as unknown as Reflector;
    const decide = jest.fn();
    const authorization = { decide } as unknown as AuthorizationDecisionService;
    const guard = new CapabilityAuthorizationGuard(reflector, authorization);

    await expect(guard.canActivate(context())).resolves.toBe(true);
    expect(decide).not.toHaveBeenCalled();
  });

  it('fails closed when local entitlements deny the capability', async () => {
    const reflector = {
      getAllAndOverride: jest.fn().mockReturnValue({
        mode: 'all-of',
        capabilities: ['authorization.role.read'],
      }),
    } as unknown as Reflector;
    const authorization = {
      decide: jest.fn().mockResolvedValue({
        allowed: false,
        code: 'INSUFFICIENT_CAPABILITY',
        revision: '2',
      }),
    } as unknown as AuthorizationDecisionService;
    const guard = new CapabilityAuthorizationGuard(reflector, authorization);

    await expect(
      guard.canActivate(context(workforcePrincipal)),
    ).rejects.toBeInstanceOf(ForbiddenException);
  });

  it('allows an authorized workforce principal', async () => {
    const reflector = {
      getAllAndOverride: jest.fn().mockReturnValue({
        mode: 'all-of',
        capabilities: ['authorization.role.read'],
      }),
    } as unknown as Reflector;
    const authorization = {
      decide: jest.fn().mockResolvedValue({
        allowed: true,
        code: 'ALLOWED',
        revision: '3',
      }),
    } as unknown as AuthorizationDecisionService;
    const guard = new CapabilityAuthorizationGuard(reflector, authorization);

    await expect(guard.canActivate(context(workforcePrincipal))).resolves.toBe(
      true,
    );
  });
});
