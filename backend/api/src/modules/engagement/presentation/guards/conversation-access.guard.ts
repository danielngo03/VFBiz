import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
} from '@nestjs/common';
import type { FastifyRequest } from 'fastify';
import type { AccessPrincipal } from '../../../../platform/security/access-principal';
import {
  ConversationAccessDeniedError,
  ConversationAccessService,
  type ConversationAuthorization,
} from '../../application/services/conversation-access.service';
import { readConversationCapabilityCookie } from '../conversation-capability-cookie';

interface ConversationRequest extends FastifyRequest {
  params: { sessionId?: string };
  vfbizConversationAuthorization?: ConversationAuthorization;
  vfbizPrincipal?: AccessPrincipal;
}

@Injectable()
export class ConversationAccessGuard implements CanActivate {
  constructor(private readonly access: ConversationAccessService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<ConversationRequest>();
    const sessionId = request.params.sessionId;
    if (sessionId === undefined) return this.deny();

    const capability = readConversationCapabilityCookie(
      request.headers.cookie,
      sessionId,
    );
    try {
      request.vfbizConversationAuthorization = await this.access.authorize({
        capability,
        now: new Date(),
        principal: request.vfbizPrincipal ?? null,
        sessionId,
      });
      return true;
    } catch (error) {
      if (error instanceof ConversationAccessDeniedError) return this.deny();
      throw error;
    }
  }

  private deny(): never {
    throw new ForbiddenException({
      code: 'CHAT_SESSION_FORBIDDEN',
      message: 'The chat session is unavailable or access was denied.',
    });
  }
}
