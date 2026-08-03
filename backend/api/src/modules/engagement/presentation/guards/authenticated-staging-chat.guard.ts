import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
  ServiceUnavailableException,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { FastifyRequest } from 'fastify';
import type { EnvironmentVariables } from '../../../../platform/config/env.schema';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';

type StagingChatRequest = FastifyRequest & {
  vfbizPrincipal?: AccessPrincipal;
};

@Injectable()
export class AuthenticatedStagingChatGuard implements CanActivate {
  constructor(
    private readonly config: ConfigService<EnvironmentVariables, true>,
  ) {}

  canActivate(context: ExecutionContext): boolean {
    if (
      this.config.get('VFBIZ_CHAT_API_MODE', { infer: true }) !==
      'authenticated-staging'
    ) {
      throw new ServiceUnavailableException({
        code: 'CHAT_RELEASE_GATE_CLOSED',
        message: 'Chat routes are not active for this deployment.',
      });
    }
    const request = context.switchToHttp().getRequest<StagingChatRequest>();
    const principal = request.vfbizPrincipal;
    if (principal === undefined) {
      throw new UnauthorizedException({
        code: 'AUTHENTICATED_STAGING_CHAT_REQUIRED',
        message: 'An authenticated customer is required.',
      });
    }
    if (principal.realm !== 'customer') {
      throw new ForbiddenException({
        code: 'CUSTOMER_CHAT_REALM_REQUIRED',
        message: 'Only a verified customer identity may use Chat.',
      });
    }
    const customerIssuer = this.config.get('VFBIZ_CUSTOMER_OIDC_ISSUER', {
      infer: true,
    });
    const customerAudience = this.config.get('VFBIZ_CUSTOMER_OIDC_AUDIENCE', {
      infer: true,
    });
    const authorizedParties = new Set(
      this.config
        .get('VFBIZ_CUSTOMER_OIDC_AUTHORIZED_PARTIES', { infer: true })
        .split(','),
    );
    if (
      principal.issuer !== customerIssuer ||
      !principal.audience.includes(customerAudience) ||
      !authorizedParties.has(principal.authorizedParty) ||
      !principal.scopes.includes('chat:use')
    ) {
      throw new ForbiddenException({
        code: 'AUTHENTICATED_STAGING_CHAT_SCOPE_REQUIRED',
        message:
          'Chat requires the exact customer issuer, client, audience and chat:use scope.',
      });
    }
    return true;
  }
}
