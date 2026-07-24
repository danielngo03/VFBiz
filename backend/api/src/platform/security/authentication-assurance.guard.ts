import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal } from './access-principal';
import {
  REQUIRED_AUTHENTICATION_METHODS,
  type RequiredAuthenticationMethodsPolicy,
} from './required-authentication-methods';

function isPolicy(
  value: unknown,
): value is RequiredAuthenticationMethodsPolicy {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<RequiredAuthenticationMethodsPolicy>;
  return (
    (candidate.mode === 'all-of' || candidate.mode === 'any-of') &&
    Array.isArray(candidate.methods) &&
    candidate.methods.length > 0 &&
    candidate.methods.every(
      (method) =>
        typeof method === 'string' && /^[a-z0-9:_-]{1,80}$/i.test(method),
    )
  );
}

@Injectable()
export class AuthenticationAssuranceGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const required = this.reflector.getAllAndOverride<unknown>(
      REQUIRED_AUTHENTICATION_METHODS,
      [context.getHandler(), context.getClass()],
    );
    if (required === undefined) return true;
    if (!isPolicy(required)) {
      throw new ForbiddenException({
        code: 'INVALID_AUTHENTICATION_ASSURANCE_POLICY',
        message: 'The authentication assurance policy is invalid.',
      });
    }
    const principal = context
      .switchToHttp()
      .getRequest<
        FastifyRequest & { vfbizPrincipal?: AccessPrincipal }
      >().vfbizPrincipal;
    const observed = new Set(principal?.authenticationMethods ?? []);
    const satisfied =
      required.mode === 'all-of'
        ? required.methods.every((method) => observed.has(method))
        : required.methods.some((method) => observed.has(method));
    if (satisfied) return true;
    throw new ForbiddenException({
      code: 'STEP_UP_AUTHENTICATION_REQUIRED',
      message: 'This operation requires a recent multi-factor session.',
    });
  }
}
