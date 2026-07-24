import type { ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import { AuthenticationGuard } from './authentication.guard';
import { LocalSessionStatusVerifier } from './local-session-status.verifier';
import { OidcTokenVerifier } from './oidc-token.verifier';

describe('AuthenticationGuard optional authentication', () => {
  const principal = {
    authenticationContext: 'urn:vfbiz:loa:1',
    authenticationMethods: ['pwd'],
    audience: ['vfbiz-api'],
    authorizedParty: 'vfbiz-customer-bff',
    issuer: 'https://ciam.example/realms/customer',
    realm: 'customer',
    scopes: ['chat:read'],
    sessionId: 'session-123',
    subject: 'customer-123',
  } as const;

  function contextFor(request: Partial<FastifyRequest>): ExecutionContext {
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

  it('allows an optional-auth route without a bearer token', async () => {
    const reflector = {
      getAllAndOverride: jest
        .fn()
        .mockReturnValueOnce(false)
        .mockReturnValueOnce(true),
    } as unknown as Reflector;
    const verify = jest.fn();
    const verifier = { verify } as unknown as OidcTokenVerifier;
    const localSessions = {
      isDenied: jest.fn(),
    } as unknown as LocalSessionStatusVerifier;
    const guard = new AuthenticationGuard(reflector, verifier, localSessions);

    await expect(guard.canActivate(contextFor({ headers: {} }))).resolves.toBe(
      true,
    );
    expect(verify).not.toHaveBeenCalled();
  });

  it('does not accept the retired NestJS customer access cookie', async () => {
    const reflector = {
      getAllAndOverride: jest
        .fn()
        .mockReturnValueOnce(false)
        .mockReturnValueOnce(false),
    } as unknown as Reflector;
    const verify = jest.fn();
    const verifier = { verify } as unknown as OidcTokenVerifier;
    const localSessions = {
      isDenied: jest.fn(),
    } as unknown as LocalSessionStatusVerifier;
    const guard = new AuthenticationGuard(reflector, verifier, localSessions);

    await expect(
      guard.canActivate(
        contextFor({
          headers: {
            cookie: '__Host-vfbiz_customer_access=header.payload.signature',
          },
        }),
      ),
    ).rejects.toMatchObject({
      response: { code: 'AUTHENTICATION_REQUIRED' },
    });
    expect(verify).not.toHaveBeenCalled();
  });

  it('verifies and attaches a bearer principal when optional auth is supplied', async () => {
    const reflector = {
      getAllAndOverride: jest
        .fn()
        .mockReturnValueOnce(false)
        .mockReturnValueOnce(true),
    } as unknown as Reflector;
    const verifier = {
      verify: jest.fn().mockResolvedValue(principal),
    } as unknown as OidcTokenVerifier;
    const request = {
      headers: { authorization: 'Bearer header.payload.signature' },
    } as Partial<FastifyRequest> & { vfbizPrincipal?: typeof principal };
    const localSessions = {
      isDenied: jest.fn().mockResolvedValue(false),
    } as unknown as LocalSessionStatusVerifier;
    const guard = new AuthenticationGuard(reflector, verifier, localSessions);

    await expect(guard.canActivate(contextFor(request))).resolves.toBe(true);
    expect(request.vfbizPrincipal).toEqual(principal);
  });

  it('rejects a token whose local session projection is revoked', async () => {
    const reflector = {
      getAllAndOverride: jest
        .fn()
        .mockReturnValueOnce(false)
        .mockReturnValueOnce(false),
    } as unknown as Reflector;
    const verifier = {
      verify: jest.fn().mockResolvedValue(principal),
    } as unknown as OidcTokenVerifier;
    const localSessions = {
      isDenied: jest.fn().mockResolvedValue(true),
    } as unknown as LocalSessionStatusVerifier;
    const guard = new AuthenticationGuard(reflector, verifier, localSessions);

    await expect(
      guard.canActivate(
        contextFor({
          headers: { authorization: 'Bearer header.payload.signature' },
        }),
      ),
    ).rejects.toMatchObject({
      response: { code: 'INVALID_ACCESS_TOKEN' },
    });
  });
});
