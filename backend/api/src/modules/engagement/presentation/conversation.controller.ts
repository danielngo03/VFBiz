import {
  Body,
  Controller,
  Get,
  Header,
  HttpCode,
  Param,
  ParseUUIDPipe,
  Post,
  Req,
  Res,
  ServiceUnavailableException,
  UseGuards,
} from '@nestjs/common';
import {
  ApiBearerAuth,
  ApiCookieAuth,
  ApiCreatedResponse,
  ApiForbiddenResponse,
  ApiOkResponse,
  ApiOperation,
  ApiServiceUnavailableResponse,
  ApiTags,
  ApiUnauthorizedResponse,
} from '@nestjs/swagger';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { Public } from '../../../platform/http/public.decorator';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { OptionalAuthentication } from '../../../platform/security/optional-authentication.decorator';
import { ConversationSessionRepository } from '../application/ports/conversation-session.repository';
import { CreateConversationSessionService } from '../application/services/create-conversation-session.service';
import { buildConversationCapabilityCookie } from './conversation-capability-cookie';
import { CreateConversationSessionDto } from './dto/create-conversation-session.dto';
import { CreateConversationMessageDto } from './dto/create-conversation-message.dto';
import { ConversationAccessGuard } from './guards/conversation-access.guard';

interface OptionalPrincipalRequest extends FastifyRequest {
  vfbizPrincipal?: AccessPrincipal;
}

@ApiTags('Chat')
@ApiCookieAuth('anonymousChatCapability')
@ApiBearerAuth('oidc')
@Controller({ path: 'chat/sessions', version: '1' })
@OptionalAuthentication()
@Public()
export class ConversationController {
  constructor(
    private readonly createConversationSession: CreateConversationSessionService,
    private readonly sessions: ConversationSessionRepository,
  ) {}

  @ApiOperation({
    operationId: 'createChatSession',
    summary: 'Create chat session',
    description:
      'Creates a governed chat session for public or authenticated customer use. Anonymous sessions receive an opaque capability cookie.',
    security: [{}, { oidc: [] }],
  })
  @ApiCreatedResponse({ description: 'Chat session created.' })
  @ApiServiceUnavailableResponse({
    description: 'No approved AI release manifest is active.',
  })
  @Post()
  @HttpCode(201)
  @Header('Cache-Control', 'no-store')
  async createSession(
    @Body() input: CreateConversationSessionDto,
    @Req() request: OptionalPrincipalRequest,
    @Res({ passthrough: true }) reply: FastifyReply,
  ) {
    const created = await this.createConversationSession.execute({
      locale: input.locale,
      principal: request.vfbizPrincipal ?? null,
      profile: input.profile,
    });
    if (created.capability !== null) {
      void reply.header(
        'Set-Cookie',
        buildConversationCapabilityCookie(
          created.session.id,
          created.capability,
          created.expiresInSeconds,
        ),
      );
    }
    return created.session;
  }

  @ApiOperation({
    operationId: 'listChatMessages',
    summary: 'List chat messages',
    description:
      'Lists messages from an authorized chat session without exposing another subject’s conversation.',
  })
  @ApiOkResponse({ description: 'Authorized chat session messages.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Get(':sessionId/messages')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ConversationAccessGuard)
  async listMessages(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
  ) {
    return this.sessions.listMessages(sessionId);
  }

  @ApiOperation({
    operationId: 'createChatMessage',
    summary: 'Send a message',
    description:
      'Accepts one customer message. The endpoint fails closed until the governed AI runtime is released.',
  })
  @ApiServiceUnavailableResponse({
    description: 'The governed AI runtime is not available yet.',
  })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Post(':sessionId/messages')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ConversationAccessGuard)
  createMessage(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Body() input: CreateConversationMessageDto,
  ): never {
    void sessionId;
    void input;
    throw new ServiceUnavailableException({
      code: 'CHAT_RUNTIME_UNAVAILABLE',
      message:
        'The governed AI runtime is unavailable until a release manifest is active.',
    });
  }
}
