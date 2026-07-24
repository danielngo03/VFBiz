import type { ExecutionContext } from '@nestjs/common';
import { ForbiddenException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import { IS_PUBLIC_ROUTE, Public } from '../http/public.decorator';
import type { AccessPrincipal } from './access-principal';
import {
  REQUIRED_SCOPES,
  RequireScopes,
  type RequiredScopesPolicy,
} from './required-scopes';
import { ScopeAuthorizationGuard } from './scope-authorization.guard';

function contextFor(
  request: Partial<FastifyRequest> & { vfbizPrincipal?: AccessPrincipal },
  targets?: {
    readonly controller: object;
    readonly handler: (...args: never[]) => unknown;
  },
): ExecutionContext {
  return {
    getClass: () => targets?.controller ?? class TestController {},
    getHandler: () => targets?.handler ?? (() => undefined),
    switchToHttp: () => ({
      getNext: () => undefined,
      getRequest: () => request,
      getResponse: () => undefined,
    }),
  } as unknown as ExecutionContext;
}

function reflectorFor(policy: unknown, publicRoute = false): Reflector {
  return {
    getAllAndOverride: jest.fn((metadataKey: string) => {
      if (metadataKey === IS_PUBLIC_ROUTE) return publicRoute || undefined;
      if (metadataKey === REQUIRED_SCOPES) return policy;
      return undefined;
    }),
  } as unknown as Reflector;
}

function principal(
  scopes: readonly string[],
  authorizedParty = 'vfbiz-customer-bff',
): AccessPrincipal {
  return {
    authenticationContext: null,
    authenticationMethods: [],
    audience: ['vfbiz-customer-api'],
    authorizedParty,
    issuer: 'https://id.example/realms/customer',
    realm: 'customer',
    scopes,
    sessionId: null,
    subject: 'customer-123',
  };
}

function forbiddenCode(action: () => unknown): string | undefined {
  try {
    action();
    return undefined;
  } catch (error) {
    if (!(error instanceof ForbiddenException)) throw error;
    return (error.getResponse() as { code?: string }).code;
  }
}

describe('ScopeAuthorizationGuard', () => {
  const allOfChatPolicy: RequiredScopesPolicy = {
    allowedAuthorizedParties: ['vfbiz-customer-bff'],
    mode: 'all-of',
    scopes: ['chat:read'],
  };

  it('allows routes without scope metadata', () => {
    const guard = new ScopeAuthorizationGuard(reflectorFor(undefined));

    expect(guard.canActivate(contextFor({ headers: {} }))).toBe(true);
  });

  it('bypasses scope authorization for explicit public metadata without a scope policy', () => {
    const guard = new ScopeAuthorizationGuard(reflectorFor(undefined, true));

    expect(guard.canActivate(contextFor({ headers: {} }))).toBe(true);
  });

  it('fails closed when public and required-scope metadata conflict', () => {
    const guard = new ScopeAuthorizationGuard(
      reflectorFor(allOfChatPolicy, true),
    );

    expect(
      forbiddenCode(() => guard.canActivate(contextFor({ headers: {} }))),
    ).toBe('INVALID_SCOPE_POLICY');
  });

  it('rejects a method scope policy inherited under a public controller', () => {
    @Public()
    class PublicController {
      @RequireScopes({
        allowedAuthorizedParties: ['vfbiz-customer-bff'],
        mode: 'all-of',
        scopes: ['chat:read'],
      })
      scopedMethod(this: void) {
        return undefined;
      }
    }
    const controller = new PublicController();
    const guard = new ScopeAuthorizationGuard(new Reflector());

    expect(
      forbiddenCode(() =>
        guard.canActivate(
          contextFor(
            {
              headers: {},
              vfbizPrincipal: principal(['chat:read']),
            },
            {
              controller: PublicController,
              handler: controller.scopedMethod,
            },
          ),
        ),
      ),
    ).toBe('INVALID_SCOPE_POLICY');
  });

  it('enforces all-of semantics and tolerates duplicate granted scopes', () => {
    const policy: RequiredScopesPolicy = {
      allowedAuthorizedParties: ['vfbiz-customer-bff'],
      mode: 'all-of',
      scopes: ['chat:read', 'chat:write'],
    };
    const guard = new ScopeAuthorizationGuard(reflectorFor(policy));

    expect(
      guard.canActivate(
        contextFor({
          headers: {},
          vfbizPrincipal: principal([
            'openid',
            'chat:read',
            'chat:read',
            'chat:write',
          ]),
        }),
      ),
    ).toBe(true);
    expect(
      forbiddenCode(() =>
        guard.canActivate(
          contextFor({
            headers: {},
            vfbizPrincipal: principal(['chat:read']),
          }),
        ),
      ),
    ).toBe('INSUFFICIENT_SCOPE');
  });

  it('enforces any-of semantics', () => {
    const policy: RequiredScopesPolicy = {
      allowedAuthorizedParties: ['vfbiz-customer-bff'],
      mode: 'any-of',
      scopes: ['chat:read', 'chat:moderate'],
    };
    const guard = new ScopeAuthorizationGuard(reflectorFor(policy));

    expect(
      guard.canActivate(
        contextFor({
          headers: {},
          vfbizPrincipal: principal(['chat:moderate']),
        }),
      ),
    ).toBe(true);
  });

  it.each([
    {
      name: 'missing principal',
      request: { headers: {} },
      code: 'SCOPE_AUTHORIZATION_FORBIDDEN',
    },
    {
      name: 'missing scopes',
      request: {
        headers: {},
        vfbizPrincipal: principal([]),
      },
      code: 'INSUFFICIENT_SCOPE',
    },
    {
      name: 'malformed scopes',
      request: {
        headers: {},
        vfbizPrincipal: principal(['chat:read', '']),
      },
      code: 'INVALID_SCOPE_CLAIM',
    },
    {
      name: 'same scope granted to an unauthorized client',
      request: {
        headers: {},
        vfbizPrincipal: principal(['chat:read'], 'vfbiz-mobile'),
      },
      code: 'INSUFFICIENT_SCOPE',
    },
  ])(
    'fails closed for $name without disclosing policy details',
    ({ request, code }) => {
      const guard = new ScopeAuthorizationGuard(reflectorFor(allOfChatPolicy));

      expect(forbiddenCode(() => guard.canActivate(contextFor(request)))).toBe(
        code,
      );
    },
  );

  it('fails closed when route metadata was malformed', () => {
    const guard = new ScopeAuthorizationGuard(
      reflectorFor({ mode: 'all-of', scopes: [] }),
    );

    expect(
      forbiddenCode(() =>
        guard.canActivate(
          contextFor({
            headers: {},
            vfbizPrincipal: principal(['chat:read']),
          }),
        ),
      ),
    ).toBe('INVALID_SCOPE_POLICY');
  });
});
