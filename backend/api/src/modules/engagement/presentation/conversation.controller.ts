import {
  Body,
  Controller,
  ForbiddenException,
  Get,
  Header,
  Headers,
  HttpException,
  HttpStatus,
  HttpCode,
  type MessageEvent,
  Param,
  ParseUUIDPipe,
  Post,
  Req,
  Res,
  ServiceUnavailableException,
  Sse,
  UseGuards,
} from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import {
  ApiBearerAuth,
  ApiAcceptedResponse,
  ApiCookieAuth,
  ApiCreatedResponse,
  ApiForbiddenResponse,
  ApiOkResponse,
  ApiOperation,
  ApiServiceUnavailableResponse,
  ApiTags,
  ApiUnauthorizedResponse,
} from '@nestjs/swagger';
import { Throttle } from '@nestjs/throttler';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { Observable } from 'rxjs';
import { Public } from '../../../platform/http/public.decorator';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import { OptionalAuthentication } from '../../../platform/security/optional-authentication.decorator';
import { ConversationSessionRepository } from '../application/ports/conversation-session.repository';
import { ConversationRuntimeService } from '../application/runtime/conversation-runtime.service';
import { CreateConversationSessionService } from '../application/services/create-conversation-session.service';
import { ConversationTurnDispatcher } from '../infrastructure/runtime/conversation-turn-dispatcher';
import { buildConversationCapabilityCookie } from './conversation-capability-cookie';
import {
  shouldCloseSlowConsumer,
  watchConversationEvents,
} from './conversation-event-stream';
import { ConversationEventReplayBuffer } from '../application/ports/conversation-event-replay-buffer';
import { ConversationEventStreamRegistry } from '../application/ports/conversation-event-stream-registry';
import { CreateConversationSessionDto } from './dto/create-conversation-session.dto';
import { CreateConversationMessageDto } from './dto/create-conversation-message.dto';
import { CancelConversationTurnDto } from './dto/cancel-conversation-turn.dto';
import { CloseConversationSessionDto } from './dto/close-conversation-session.dto';
import { RequestConversationHandoffDto } from './dto/request-conversation-handoff.dto';
import { ConversationAccessGuard } from './guards/conversation-access.guard';
import { ChatThrottlerGuard } from './guards/chat-throttler.guard';

const SSE_HEARTBEAT_INTERVAL_MS = 15_000;
const SSE_MAXIMUM_CONNECTIONS_PER_SESSION = 3;
const SSE_MAXIMUM_LIFETIME_MS = 5 * 60_000;
const SSE_POLL_INTERVAL_MS = 1_000;
const SSE_SOCKET_BUFFER_LIMIT_BYTES = 64 * 1024;
const SSE_RECONNECT_DELAY_MS = 1_000;

interface OptionalPrincipalRequest extends FastifyRequest {
  vfbizConversationAuthorization?: {
    accessScope: import('../domain/runtime/conversation-runtime').ConversationAccessScope;
  };
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
    private readonly runtime: ConversationRuntimeService,
    private readonly replayBuffer: ConversationEventReplayBuffer,
    private readonly streamRegistry: ConversationEventStreamRegistry,
    private readonly dispatcher: ConversationTurnDispatcher,
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
  @UseGuards(ChatThrottlerGuard)
  @Throttle({ default: { limit: 5, ttl: 60_000 } })
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
    operationId: 'getChatSession',
    summary: 'Get chat session',
    description:
      'Reads session metadata and runtime status for an authorized chat session.',
  })
  @ApiOkResponse({ description: 'Authorized chat session summary.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Get(':sessionId')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ConversationAccessGuard)
  async getSession(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Req() request: OptionalPrincipalRequest,
  ) {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    const [summary, runtimeStatus] = await Promise.all([
      this.sessions.findSessionSummary(sessionId),
      this.runtime.getRuntimeStatus({
        accessScope: authorization.accessScope,
        sessionId,
      }),
    ]);
    if (summary === null) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    return {
      conversationVersion: runtimeStatus.conversationVersion,
      createdAt: summary.createdAt,
      expiresAt: summary.expiresAt,
      id: summary.id,
      locale: summary.locale,
      profile: summary.profile,
      retentionUntil: summary.retentionUntil,
      status: runtimeStatus.status,
    };
  }

  @ApiOperation({
    operationId: 'streamChatEvents',
    summary: 'Stream chat events',
    description:
      'Server-sent events for an authorized chat session. Reconnects replay from Last-Event-ID against the durable event log; SSE is a projection, never the source of truth.',
  })
  @ApiOkResponse({ description: 'text/event-stream of durable chat events.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Sse(':sessionId/events')
  @UseGuards(ConversationAccessGuard)
  streamEvents(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Headers('last-event-id') lastEventId: string | undefined,
    @Req() request: OptionalPrincipalRequest,
  ): Observable<MessageEvent> {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    const accessScope = authorization.accessScope;
    return new Observable<MessageEvent>((subscriber) => {
      const controller = new AbortController();
      void (async () => {
        let closing = false;
        let lastDeliveredCursor = lastEventId ?? null;
        const now = new Date();
        const lease = await this.streamRegistry.acquire({
          connectionId: randomUUID(),
          expiresAt: new Date(now.getTime() + SSE_MAXIMUM_LIFETIME_MS),
          maximumConnections: SSE_MAXIMUM_CONNECTIONS_PER_SESSION,
          now,
          sessionId,
        });
        if (lease === null) {
          subscriber.error(
            new HttpException(
              {
                code: 'CHAT_EVENT_STREAM_CAPACITY_EXCEEDED',
                message:
                  'The event stream is temporarily unavailable. Reconnect with the last event ID.',
              },
              HttpStatus.TOO_MANY_REQUESTS,
            ),
          );
          return;
        }
        const closeSlowConsumer = () => {
          if (closing || !socketBufferExceeded(request)) return false;
          closing = true;
          subscriber.next({
            data: {
              lastEventId: lastDeliveredCursor,
              reason: 'slow_consumer',
              retryAfterMs: SSE_RECONNECT_DELAY_MS,
            },
            type: 'stream.reconnect_required',
          });
          controller.abort();
          return true;
        };
        const heartbeat = setInterval(() => {
          if (closeSlowConsumer()) return;
          subscriber.next({ data: {}, type: 'heartbeat' });
        }, SSE_HEARTBEAT_INTERVAL_MS);
        const lifetime = setTimeout(
          () => controller.abort(),
          SSE_MAXIMUM_LIFETIME_MS,
        );
        try {
          for await (const item of watchConversationEvents(this.runtime, {
            accessScope,
            afterCursor: lastEventId ?? null,
            pollIntervalMs: SSE_POLL_INTERVAL_MS,
            replayBuffer: this.replayBuffer,
            sessionId,
            signal: controller.signal,
          })) {
            if (closeSlowConsumer()) break;
            if (item.kind === 'control') {
              closing = true;
              subscriber.next({ data: item.data, type: item.type });
              controller.abort();
              break;
            }
            const event = item.event;
            subscriber.next({
              data: event.payload,
              id: event.cursor,
              type: event.type,
            });
            lastDeliveredCursor = event.cursor;
            if (closeSlowConsumer()) break;
          }
          subscriber.complete();
        } catch (error) {
          subscriber.error(error);
        } finally {
          clearInterval(heartbeat);
          clearTimeout(lifetime);
          await this.streamRegistry.release(lease);
        }
      })();
      return () => {
        controller.abort();
      };
    });
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
    @Req() request: OptionalPrincipalRequest,
  ) {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    return this.sessions.listMessages(sessionId, authorization.accessScope);
  }

  @ApiOperation({
    operationId: 'createChatMessage',
    summary: 'Send a message',
    description:
      'Accepts one customer message. The endpoint fails closed until the governed AI runtime is released.',
  })
  @ApiAcceptedResponse({
    description:
      'Message durably accepted into the session inbox for asynchronous processing.',
  })
  @ApiServiceUnavailableResponse({ description: 'AI runtime is disabled.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Post(':sessionId/messages')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ChatThrottlerGuard, ConversationAccessGuard)
  @Throttle({ default: { limit: 20, ttl: 60_000 } })
  @HttpCode(202)
  async createMessage(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Body() input: CreateConversationMessageDto,
    @Req() request: OptionalPrincipalRequest,
  ) {
    if (!this.dispatcher.isEnabled()) {
      throw new ServiceUnavailableException({
        code: 'CHAT_RUNTIME_UNAVAILABLE',
        message: 'The governed AI runtime is disabled.',
      });
    }
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    const accepted = await this.runtime.acceptMessage({
      accessScope: authorization.accessScope,
      budget: { maxCostMicros: 250_000, maxModelTokens: 4_096 },
      clientMessageId: input.clientMessageId,
      content: input.content,
      expectedVersion: input.expectedVersion,
      sessionId,
    });
    this.dispatcher.kick();
    return accepted;
  }

  @ApiOperation({
    operationId: 'cancelChatTurn',
    summary: 'Cancel chat turn',
    description:
      'Durably cancels an accepted or running turn. Provider cancellation is delivered asynchronously from the transactional outbox.',
  })
  @ApiOkResponse({ description: 'Turn cancellation committed.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Post(':sessionId/turns/:turnId/cancel')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ConversationAccessGuard)
  async cancelTurn(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Param('turnId', new ParseUUIDPipe({ version: '4' })) turnId: string,
    @Body() input: CancelConversationTurnDto,
    @Req() request: OptionalPrincipalRequest,
  ) {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    const cancelled = await this.runtime.cancelTurnByCustomer({
      accessScope: authorization.accessScope,
      expectedVersion: input.expectedVersion,
      sessionId,
      turnId,
    });
    this.dispatcher.kick();
    return cancelled;
  }

  @ApiOperation({
    operationId: 'closeChatSession',
    summary: 'Close chat session',
    description:
      'Durably closes the session so no further message or turn can start. Already-persisted history remains readable until retention expiry.',
  })
  @ApiOkResponse({ description: 'Session close committed.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Post(':sessionId/close')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ConversationAccessGuard)
  async closeSession(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Body() input: CloseConversationSessionDto,
    @Req() request: OptionalPrincipalRequest,
  ) {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    return this.runtime.closeSession({
      accessScope: authorization.accessScope,
      expectedVersion: input.expectedVersion,
      sessionId,
    });
  }

  @ApiOperation({
    operationId: 'requestChatHandoff',
    summary: 'Request human handoff',
    description:
      'Explicitly requests a human support handoff for this session. This creates only a governed recommendation/request boundary; contact-center lifecycle is owned separately.',
  })
  @ApiOkResponse({ description: 'Handoff request committed.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Post(':sessionId/handoff')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ConversationAccessGuard)
  async requestHandoff(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Body() input: RequestConversationHandoffDto,
    @Req() request: OptionalPrincipalRequest,
  ) {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    return this.runtime.requestHandoff({
      accessScope: authorization.accessScope,
      expectedVersion: input.expectedVersion,
      sessionId,
    });
  }
}

function socketBufferExceeded(request: FastifyRequest): boolean {
  return shouldCloseSlowConsumer(
    request.raw.socket.writableLength,
    SSE_SOCKET_BUFFER_LIMIT_BYTES,
  );
}
