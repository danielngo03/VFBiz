import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal } from './access-principal';
import { isRequiredRolesPolicy, REQUIRED_ROLES } from './required-roles';

interface AuthenticatedRequest extends FastifyRequest {
  vfbizPrincipal?: AccessPrincipal;
}

@Injectable()
export class RoleAuthorizationGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const policy = this.reflector.getAllAndOverride<unknown>(REQUIRED_ROLES, [
      context.getHandler(),
      context.getClass(),
    ]);
    if (policy === undefined) return true;
    if (!isRequiredRolesPolicy(policy)) {
      throw new ForbiddenException({
        code: 'INVALID_ROLE_POLICY',
        message: 'The operation role policy is invalid.',
      });
    }

    const principal = context
      .switchToHttp()
      .getRequest<AuthenticatedRequest>().vfbizPrincipal;
    if (principal === undefined || !Array.isArray(principal.roles)) {
      throw new ForbiddenException({
        code: 'ROLE_AUTHORIZATION_FORBIDDEN',
        message: 'A verified access principal with roles is required.',
      });
    }

    const granted = new Set(principal.roles);
    const allowed =
      policy.mode === 'all-of'
        ? policy.roles.every((role) => granted.has(role))
        : policy.roles.some((role) => granted.has(role));
    if (allowed) return true;

    throw new ForbiddenException({
      code: 'INSUFFICIENT_ROLE',
      message: 'The workforce identity does not grant this operation.',
    });
  }
}
