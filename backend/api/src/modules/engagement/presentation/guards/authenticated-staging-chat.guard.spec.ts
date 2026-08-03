import type { ExecutionContext } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { FastifyRequest } from 'fastify';
import type { EnvironmentVariables } from '../../../../platform/config/env.schema';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import { AuthenticatedStagingChatGuard } from './authenticated-staging-chat.guard';

function contextFor(
  request: Partial<FastifyRequest> & {
    vfbizPrincipal?: AccessPrincipal;
  },
): ExecutionContext {
  return {
    switchToHttp: () => ({
      getRequest: () => request,
    }),
  } as ExecutionContext;
}

function config(mode: EnvironmentVariables['VFBIZ_CHAT_API_MODE']) {
  const values = {
    VFBIZ_CHAT_API_MODE: mode,
    VFBIZ_CUSTOMER_OIDC_AUDIENCE: 'vfbiz-customer-api',
    VFBIZ_CUSTOMER_OIDC_AUTHORIZED_PARTIES: 'vfbiz-customer-bff,vfbiz-mobile',
    VFBIZ_CUSTOMER_OIDC_ISSUER: 'https://identity.example.test/customer',
  } satisfies Partial<EnvironmentVariables>;
  return {
    get: (key: string): string => {
      const value = values[key as keyof typeof values];
      if (value === undefined) {
        throw new Error(`Unexpected configuration key: ${key}`);
      }
      return value;
    },
  } as unknown as ConfigService<EnvironmentVariables, true>;
}

const customerPrincipal = {
  authenticationContext: null,
  authenticationMethods: [],
  audience: ['vfbiz-customer-api'],
  authorizedParty: 'vfbiz-customer-bff',
  issuer: 'https://identity.example.test/customer',
  realm: 'customer',
  roles: [],
  scopes: ['chat:use'],
  sessionId: null,
  subject: 'customer-1',
} satisfies AccessPrincipal;

describe('AuthenticatedStagingChatGuard', () => {
  it('fails closed while routes are disabled', () => {
    const guard = new AuthenticatedStagingChatGuard(config('disabled'));
    expect(() => guard.canActivate(contextFor({}))).toThrow(
      'Chat routes are not active',
    );
  });

  it('requires an authenticated principal', () => {
    const guard = new AuthenticatedStagingChatGuard(
      config('authenticated-staging'),
    );
    expect(() => guard.canActivate(contextFor({}))).toThrow(
      'An authenticated customer is required',
    );
  });

  it('accepts customer realm and rejects workforce realm', () => {
    const guard = new AuthenticatedStagingChatGuard(
      config('authenticated-staging'),
    );
    expect(
      guard.canActivate(contextFor({ vfbizPrincipal: customerPrincipal })),
    ).toBe(true);
    expect(() =>
      guard.canActivate(
        contextFor({
          vfbizPrincipal: {
            ...customerPrincipal,
            issuer: 'https://identity.example.test/workforce',
            realm: 'workforce',
          },
        }),
      ),
    ).toThrow('Only a verified customer identity may use Chat');
  });

  it.each([
    {
      change: { issuer: 'https://identity.example.test/other' },
      name: 'wrong issuer',
    },
    {
      change: { audience: ['other-api'] },
      name: 'wrong audience',
    },
    {
      change: { authorizedParty: 'unapproved-client' },
      name: 'unapproved client',
    },
    {
      change: { scopes: [] },
      name: 'missing chat scope',
    },
  ])('rejects $name', ({ change }) => {
    const guard = new AuthenticatedStagingChatGuard(
      config('authenticated-staging'),
    );
    expect(() =>
      guard.canActivate(
        contextFor({
          vfbizPrincipal: { ...customerPrincipal, ...change },
        }),
      ),
    ).toThrow('exact customer issuer');
  });
});
