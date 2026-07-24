import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import { IS_PUBLIC_ROUTE } from '../http/public.decorator';
import { AccessPrincipal } from './access-principal';
import { LocalSessionStatusVerifier } from './local-session-status.verifier';
import { OidcTokenVerifier } from './oidc-token.verifier';
import { OPTIONAL_AUTHENTICATION } from './optional-authentication.decorator';

interface AuthenticatedRequest extends FastifyRequest {
  vfbizPrincipal?: AccessPrincipal;
}

@Injectable()
export class AuthenticationGuard implements CanActivate {
  constructor(
    private readonly reflector: Reflector,
    private readonly verifier: OidcTokenVerifier,
    private readonly localSessions: LocalSessionStatusVerifier,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const publicRoute = this.reflector.getAllAndOverride<boolean>(
      IS_PUBLIC_ROUTE,
      [context.getHandler(), context.getClass()],
    );
    const optionalAuthentication = this.reflector.getAllAndOverride<boolean>(
      OPTIONAL_AUTHENTICATION,
      [context.getHandler(), context.getClass()],
    );
    if (publicRoute && !optionalAuthentication) return true;

    const request = context.switchToHttp().getRequest<AuthenticatedRequest>();
    const authorization = request.headers.authorization;
    if (authorization === undefined) {
      if (optionalAuthentication) return true;
      throw new UnauthorizedException({
        code: 'AUTHENTICATION_REQUIRED',
        message: 'A bearer access token is required.',
      });
    }
    const token = this.tokenFromAuthorizationHeader(authorization);
    try {
      const principal = await this.verifier.verify(token);
      if (await this.localSessions.isDenied(principal)) {
        throw new Error('The local session projection denies this session.');
      }
      request.vfbizPrincipal = principal;
      return true;
    } catch {
      throw new UnauthorizedException({
        code: 'INVALID_ACCESS_TOKEN',
        message: 'The bearer access token could not be verified.',
      });
    }
  }

  private tokenFromAuthorizationHeader(authorization: string): string {
    const [scheme, token, extra] = authorization.split(' ');
    if (
      scheme !== 'Bearer' ||
      token === undefined ||
      extra !== undefined ||
      token.split('.').length !== 3
    ) {
      throw new UnauthorizedException({
        code: 'INVALID_ACCESS_TOKEN',
        message: 'The bearer access token is malformed.',
      });
    }
    return token;
  }
}
