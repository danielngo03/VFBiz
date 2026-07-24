import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal, IdentityRealm } from './access-principal';
import { REQUIRED_IDENTITY_REALM } from './required-identity-realm';

interface AuthenticatedRequest extends FastifyRequest {
  vfbizPrincipal?: AccessPrincipal;
}

@Injectable()
export class IdentityRealmGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredRealm = this.reflector.getAllAndOverride<IdentityRealm>(
      REQUIRED_IDENTITY_REALM,
      [context.getHandler(), context.getClass()],
    );
    if (requiredRealm === undefined) return true;

    const request = context.switchToHttp().getRequest<AuthenticatedRequest>();
    if (request.vfbizPrincipal?.realm === requiredRealm) return true;
    throw new ForbiddenException({
      code: 'IDENTITY_REALM_FORBIDDEN',
      message: `This operation requires a ${requiredRealm} identity.`,
    });
  }
}
