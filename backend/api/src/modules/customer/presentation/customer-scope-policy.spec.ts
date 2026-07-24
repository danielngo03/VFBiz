import type { ExecutionContext } from '@nestjs/common';
import { ForbiddenException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { IdentityRealmGuard } from '../../../platform/security/identity-realm.guard';
import {
  REQUIRED_SCOPES,
  type RequiredScopesPolicy,
} from '../../../platform/security/required-scopes';
import { ScopeAuthorizationGuard } from '../../../platform/security/scope-authorization.guard';
import { CustomerGarageController } from './customer-garage.controller';
import { CustomerController } from './customer.controller';
import {
  CUSTOMER_AUTHORIZED_PARTIES,
  CUSTOMER_OPERATION_SCOPES,
} from './customer-scope-policy';

type ControllerMethod = (...args: never[]) => unknown;

function controllerMethod(
  controller: { readonly prototype: object },
  methodName: string,
): ControllerMethod {
  const handler: unknown = Object.getOwnPropertyDescriptor(
    controller.prototype,
    methodName,
  )?.value;
  if (typeof handler !== 'function') {
    throw new TypeError(`Controller method ${methodName} was not found.`);
  }
  return handler as ControllerMethod;
}

function contextFor(
  controller: object,
  handler: ControllerMethod,
  principal: AccessPrincipal,
): ExecutionContext {
  const request = {
    headers: {},
    vfbizPrincipal: principal,
  } as Partial<FastifyRequest> & { vfbizPrincipal: AccessPrincipal };
  return {
    getClass: () => controller,
    getHandler: () => handler,
    switchToHttp: () => ({
      getNext: () => undefined,
      getRequest: () => request,
      getResponse: () => undefined,
    }),
  } as unknown as ExecutionContext;
}

function principal(
  realm: 'customer' | 'workforce',
  scopes: readonly string[],
): AccessPrincipal {
  return {
    authenticationContext: null,
    authenticationMethods: [],
    audience: [`vfbiz-${realm}-api`],
    authorizedParty: `vfbiz-${realm}-bff`,
    issuer: `https://id.example/realms/${realm}`,
    realm,
    scopes,
    sessionId: null,
    subject: `${realm}-subject`,
  };
}

function requiredPolicy(handler: ControllerMethod): RequiredScopesPolicy {
  return Reflect.getMetadata(REQUIRED_SCOPES, handler) as RequiredScopesPolicy;
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

describe('Customer operation scope matrix', () => {
  const getProfile = controllerMethod(CustomerController, 'getProfile');
  const updateProfile = controllerMethod(CustomerController, 'updateProfile');
  const listConsents = controllerMethod(CustomerController, 'listConsents');
  const updateConsents = controllerMethod(CustomerController, 'updateConsents');
  const createDataRequest = controllerMethod(
    CustomerController,
    'createDataRequest',
  );
  const listGarage = controllerMethod(CustomerGarageController, 'list');
  const createGarage = controllerMethod(CustomerGarageController, 'create');
  const updateGarage = controllerMethod(CustomerGarageController, 'update');
  const archiveGarage = controllerMethod(CustomerGarageController, 'archive');

  it.each([
    [getProfile, CUSTOMER_OPERATION_SCOPES.profileRead],
    [updateProfile, CUSTOMER_OPERATION_SCOPES.profileWrite],
    [listConsents, CUSTOMER_OPERATION_SCOPES.consentRead],
    [updateConsents, CUSTOMER_OPERATION_SCOPES.consentWrite],
    [createDataRequest, CUSTOMER_OPERATION_SCOPES.dataRequestCreate],
    [listGarage, CUSTOMER_OPERATION_SCOPES.garageRead],
    [createGarage, CUSTOMER_OPERATION_SCOPES.garageWrite],
    [updateGarage, CUSTOMER_OPERATION_SCOPES.garageWrite],
    [archiveGarage, CUSTOMER_OPERATION_SCOPES.garageWrite],
  ])('declares the expected all-of policy for %p', (handler, scope) => {
    expect(requiredPolicy(handler)).toEqual({
      allowedAuthorizedParties: CUSTOMER_AUTHORIZED_PARTIES,
      mode: 'all-of',
      scopes: [scope],
    });
  });

  it('rejects missing and wrong operation scopes before profile access', () => {
    const reflector = new Reflector();
    const guard = new ScopeAuthorizationGuard(reflector);

    expect(
      forbiddenCode(() =>
        guard.canActivate(
          contextFor(CustomerController, getProfile, principal('customer', [])),
        ),
      ),
    ).toBe('INSUFFICIENT_SCOPE');
    expect(
      forbiddenCode(() =>
        guard.canActivate(
          contextFor(
            CustomerController,
            getProfile,
            principal('customer', [CUSTOMER_OPERATION_SCOPES.profileWrite]),
          ),
        ),
      ),
    ).toBe('INSUFFICIENT_SCOPE');
  });

  it('rejects a workforce realm even when it presents the operation scope', () => {
    const guard = new IdentityRealmGuard(new Reflector());

    expect(
      forbiddenCode(() =>
        guard.canActivate(
          contextFor(
            CustomerController,
            getProfile,
            principal('workforce', [CUSTOMER_OPERATION_SCOPES.profileRead]),
          ),
        ),
      ),
    ).toBe('IDENTITY_REALM_FORBIDDEN');
  });
});
