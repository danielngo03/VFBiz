import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import { IS_PUBLIC_ROUTE } from '../http/public.decorator';
import type { AccessPrincipal } from './access-principal';
import {
  isRequiredScopesPolicy,
  isRfc6749ScopeToken,
  REQUIRED_SCOPES,
} from './required-scopes';

interface AuthenticatedRequest extends FastifyRequest {
  vfbizPrincipal?: AccessPrincipal;
}

@Injectable()
export class ScopeAuthorizationGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const metadataTargets = [context.getHandler(), context.getClass()];
    const publicRoute =
      this.reflector.getAllAndOverride<boolean>(
        IS_PUBLIC_ROUTE,
        metadataTargets,
      ) === true;
    const policy = this.reflector.getAllAndOverride<unknown>(
      REQUIRED_SCOPES,
      metadataTargets,
    );
    if (publicRoute && policy !== undefined) {
      throw new ForbiddenException({
        code: 'INVALID_SCOPE_POLICY',
        message: 'Public and protected scope metadata cannot be combined.',
      });
    }
    if (publicRoute) return true;
    if (policy === undefined) return true;
    if (!isRequiredScopesPolicy(policy)) {
      throw new ForbiddenException({
        code: 'INVALID_SCOPE_POLICY',
        message: 'The operation scope policy is invalid.',
      });
    }

    const request = context.switchToHttp().getRequest<AuthenticatedRequest>();
    const principal = request.vfbizPrincipal;
    if (principal === undefined) {
      throw new ForbiddenException({
        code: 'SCOPE_AUTHORIZATION_FORBIDDEN',
        message: 'A verified access principal is required for this operation.',
      });
    }
    if (
      !Array.isArray(principal.scopes) ||
      !principal.scopes.every(isRfc6749ScopeToken)
    ) {
      throw new ForbiddenException({
        code: 'INVALID_SCOPE_CLAIM',
        message: 'The access token contains an invalid scope claim.',
      });
    }

    const grantedScopes = new Set(principal.scopes);
    const authorizedPartyAllowed = policy.allowedAuthorizedParties.includes(
      principal.authorizedParty,
    );
    const scopeAllowed =
      policy.mode === 'all-of'
        ? policy.scopes.every((scope) => grantedScopes.has(scope))
        : policy.scopes.some((scope) => grantedScopes.has(scope));
    if (authorizedPartyAllowed && scopeAllowed) return true;

    throw new ForbiddenException({
      code: 'INSUFFICIENT_SCOPE',
      message: 'The access token does not grant this operation.',
    });
  }
}
