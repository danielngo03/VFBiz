import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import {
  isRequiredCapabilitiesPolicy,
  REQUIRED_CAPABILITIES,
} from '../../../platform/security/required-capabilities';
import { AuthorizationDecisionService } from '../application/services/authorization-decision.service';

@Injectable()
export class CapabilityAuthorizationGuard implements CanActivate {
  constructor(
    private readonly reflector: Reflector,
    private readonly authorization: AuthorizationDecisionService,
  ) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const policy = this.reflector.getAllAndOverride<unknown>(
      REQUIRED_CAPABILITIES,
      [context.getHandler(), context.getClass()],
    );
    if (policy === undefined) return true;
    if (!isRequiredCapabilitiesPolicy(policy)) {
      throw new ForbiddenException({
        code: 'INVALID_CAPABILITY_POLICY',
        message: 'The operation capability policy is invalid.',
      });
    }
    const principal = context
      .switchToHttp()
      .getRequest<
        FastifyRequest & { vfbizPrincipal?: AccessPrincipal }
      >().vfbizPrincipal;
    if (principal === undefined || principal.realm !== 'workforce') {
      throw new ForbiddenException({
        code: 'CAPABILITY_AUTHORIZATION_FORBIDDEN',
        message: 'A verified workforce principal is required.',
      });
    }
    const decision = await this.authorization.decide(principal, policy);
    if (decision.allowed) return true;
    throw new ForbiddenException({
      code: decision.code,
      message:
        decision.code === 'STEP_UP_AUTHENTICATION_REQUIRED'
          ? 'This operation requires a recent multi-factor session.'
          : 'The workforce identity is not authorized for this operation.',
    });
  }
}
