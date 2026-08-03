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
  ServiceUnavailableException,
  Sse,
  UseGuards,
} from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import {
  ApiBearerAuth,
  ApiAcceptedResponse,
  ApiCreatedResponse,
  ApiForbiddenResponse,
  ApiOkResponse,
  ApiOperation,
  ApiServiceUnavailableResponse,
  ApiTags,
  ApiUnauthorizedResponse,
} from '@nestjs/swagger';
import { Throttle } from '@nestjs/throttler';
import type { FastifyRequest } from 'fastify';
import { Observable } from 'rxjs';
import type { AccessPrincipal } from '../../../platform/security/access-principal';
import type { ConversationPublicEvent } from '../domain/runtime/conversation-runtime';
import { ConversationSessionRepository } from '../application/ports/conversation-session.repository';
import { ConversationRuntimeService } from '../application/runtime/conversation-runtime.service';
import { CreateConversationSessionService } from '../application/services/create-conversation-session.service';
import { ConversationTurnDispatcher } from '../infrastructure/runtime/conversation-turn-dispatcher';
import {
  shouldCloseSlowConsumer,
  watchConversationEvents,
} from './conversation-event-stream';
import { ConversationEventReplayBuffer } from '../application/ports/conversation-event-replay-buffer';
import { ConversationEventStreamRegistry } from '../application/ports/conversation-event-stream-registry';
import { CreateConversationSessionDto } from './dto/create-conversation-session.dto';
import { CreateConversationMessageDto } from './dto/create-conversation-message.dto';
import { CancelConversationTurnDto } from './dto/cancel-conversation-turn.dto';
import { RequestConversationHandoffDto } from './dto/request-conversation-handoff.dto';
import { ConversationAccessGuard } from './guards/conversation-access.guard';
import { ChatThrottlerGuard } from './guards/chat-throttler.guard';
import { AuthenticatedStagingChatGuard } from './guards/authenticated-staging-chat.guard';
import { StagingChatLiveControlGuard } from './guards/staging-chat-live-control.guard';

const SSE_HEARTBEAT_INTERVAL_MS = 15_000;
const SSE_MAXIMUM_CONNECTIONS_PER_SESSION = 3;
const SSE_MAXIMUM_LIFETIME_MS = 5 * 60_000;
const SSE_POLL_INTERVAL_MS = 1_000;
const SSE_SOCKET_BUFFER_LIMIT_BYTES = 64 * 1024;
const SSE_RECONNECT_DELAY_MS = 1_000;

interface AuthenticatedPrincipalRequest extends FastifyRequest {
  vfbizConversationAuthorization?: {
    accessScope: import('../domain/runtime/conversation-runtime').ConversationAccessScope;
  };
  vfbizPrincipal?: AccessPrincipal;
}

@ApiTags('Chat')
@ApiBearerAuth('oidc')
@Controller({ path: 'chat/sessions', version: '1' })
@UseGuards(AuthenticatedStagingChatGuard, StagingChatLiveControlGuard)
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
    operationId: 'createConversationSession',
    summary: 'Create chat session',
    description:
      'Creates a governed staging chat session for a verified customer identity.',
    security: [{ oidc: [] }],
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
    @Req() request: AuthenticatedPrincipalRequest,
  ) {
    const principal = request.vfbizPrincipal;
    if (principal === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHENTICATED_PRINCIPAL_MISSING',
        message: 'The verified customer identity is unavailable.',
      });
    }
    const created = await this.createConversationSession.execute({
      locale: input.locale,
      principal,
      profile: 'authenticated_customer',
    });
    return {
      ...created.session,
      status: 'active' as const,
      version: 0,
    };
  }

  @ApiOperation({
    operationId: 'getConversationSession',
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
    @Req() request: AuthenticatedPrincipalRequest,
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
      version: runtimeStatus.conversationVersion,
      createdAt: summary.createdAt,
      expiresAt: summary.expiresAt,
      id: summary.id,
      locale: summary.locale,
      profile: summary.profile,
      retentionUntil: summary.retentionUntil,
      status: publicConversationStatus(runtimeStatus.status),
    };
  }

  @ApiOperation({
    operationId: 'streamConversationEvents',
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
    @Req() request: AuthenticatedPrincipalRequest,
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
        const correlationId = requestCorrelationId(request);
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
            data: controlSseFrame({
              correlationId,
              data: {
                lastEventId: lastDeliveredCursor,
                reason: 'slow_consumer',
                retryAfterMs: SSE_RECONNECT_DELAY_MS,
              },
              sessionId,
              type: 'stream.reconnect_required',
            }),
            type: 'stream.reconnect_required',
          });
          controller.abort();
          return true;
        };
        const heartbeat = setInterval(() => {
          if (closeSlowConsumer()) return;
          subscriber.next({
            data: controlSseFrame({
              correlationId,
              data: {},
              sessionId,
              type: 'heartbeat',
            }),
            type: 'heartbeat',
          });
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
              subscriber.next({
                data: controlSseFrame({
                  correlationId,
                  data: item.data,
                  sessionId,
                  type: item.type,
                }),
                type: item.type,
              });
              controller.abort();
              break;
            }
            const event = item.event;
            subscriber.next({
              data: toCustomerSseEvent(event, correlationId),
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
    operationId: 'listConversationMessages',
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
    @Req() request: AuthenticatedPrincipalRequest,
  ) {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    const items = await this.sessions.listMessages(
      sessionId,
      authorization.accessScope,
    );
    return { items, nextCursor: null };
  }

  @ApiOperation({
    operationId: 'enqueueConversationMessage',
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
    @Headers('idempotency-key') idempotencyKey: string | undefined,
    @Req() request: AuthenticatedPrincipalRequest,
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
    assertMessageIdempotencyKey(idempotencyKey, input.clientMessageId);
    const accepted = await this.runtime.acceptMessage({
      accessScope: authorization.accessScope,
      budget: input.budget,
      clientMessageId: input.clientMessageId,
      content: input.content,
      expectedVersion: input.expectedVersion,
      sessionId,
    });
    this.dispatcher.kick();
    return { ...accepted, kind: 'message.accepted' as const };
  }

  @ApiOperation({
    operationId: 'cancelConversationTurn',
    summary: 'Cancel chat turn',
    description:
      'Durably cancels an accepted or running turn. Provider cancellation is delivered asynchronously from the transactional outbox.',
  })
  @ApiAcceptedResponse({ description: 'Turn cancellation committed.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Post(':sessionId/turns/:turnId/cancel')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ConversationAccessGuard)
  @HttpCode(202)
  async cancelTurn(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Param('turnId', new ParseUUIDPipe({ version: '4' })) turnId: string,
    @Body() input: CancelConversationTurnDto,
    @Req() request: AuthenticatedPrincipalRequest,
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
    return {
      conversationVersion: cancelled.conversationVersion,
      eventCursor: cancelled.eventCursor,
      sessionId,
      status: 'accepted' as const,
    };
  }

  @ApiOperation({
    operationId: 'closeConversationSession',
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
    @Headers('if-match') ifMatch: string | undefined,
    @Req() request: AuthenticatedPrincipalRequest,
  ) {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    await this.runtime.closeSession({
      accessScope: authorization.accessScope,
      expectedVersion: parseConversationEtag(ifMatch),
      sessionId,
    });
    const summary = await this.sessions.findSessionSummary(sessionId);
    if (summary === null) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    const status = await this.runtime.getRuntimeStatus({
      accessScope: authorization.accessScope,
      sessionId,
    });
    return {
      ...summary,
      status: publicConversationStatus(status.status),
      version: status.conversationVersion,
    };
  }

  @ApiOperation({
    operationId: 'requestConversationHandoff',
    summary: 'Request human handoff',
    description:
      'Explicitly requests a human support handoff for this session. This creates only a governed recommendation/request boundary; contact-center lifecycle is owned separately.',
  })
  @ApiAcceptedResponse({ description: 'Handoff request committed.' })
  @ApiUnauthorizedResponse({
    description: 'Missing or invalid customer token.',
  })
  @ApiForbiddenResponse({
    description: 'Invalid anonymous capability or subject access.',
  })
  @Post(':sessionId/handoff')
  @Header('Cache-Control', 'no-store')
  @UseGuards(ConversationAccessGuard)
  @HttpCode(202)
  async requestHandoff(
    @Param('sessionId', new ParseUUIDPipe({ version: '4' })) sessionId: string,
    @Body() input: RequestConversationHandoffDto,
    @Req() request: AuthenticatedPrincipalRequest,
  ) {
    const authorization = request.vfbizConversationAuthorization;
    if (authorization === undefined) {
      throw new ForbiddenException({
        code: 'CHAT_AUTHORIZATION_CONTEXT_MISSING',
        message: 'The authorized chat context is unavailable.',
      });
    }
    const handoff = await this.runtime.requestHandoff({
      accessScope: authorization.accessScope,
      expectedVersion: input.expectedVersion,
      sessionId,
    });
    return {
      conversationVersion: handoff.conversationVersion,
      eventCursor: handoff.eventCursor,
      sessionId,
      status: 'accepted' as const,
    };
  }
}

function publicConversationStatus(
  status: 'closed' | 'handoff' | 'open',
): 'active' | 'closed' | 'handoff' {
  return status === 'open' ? 'active' : status;
}

function parseConversationEtag(value: string | undefined): number {
  const match = /^(?:W\/)?"conversation-(0|[1-9][0-9]*)"$/u.exec(value ?? '');
  const version = match === null ? Number.NaN : Number(match[1]);
  if (!Number.isSafeInteger(version)) {
    throw new HttpException(
      {
        code: 'VERSION_CONFLICT',
        message: 'A valid conversation If-Match revision is required.',
      },
      HttpStatus.PRECONDITION_FAILED,
    );
  }
  return version;
}

function assertMessageIdempotencyKey(
  value: string | undefined,
  clientMessageId: string,
): void {
  if (value !== clientMessageId) {
    throw new HttpException(
      {
        code: 'CHAT_IDEMPOTENCY_KEY_MISMATCH',
        message:
          'Idempotency-Key must match clientMessageId for message replay.',
      },
      HttpStatus.BAD_REQUEST,
    );
  }
}

function socketBufferExceeded(request: FastifyRequest): boolean {
  return shouldCloseSlowConsumer(
    request.raw.socket.writableLength,
    SSE_SOCKET_BUFFER_LIMIT_BYTES,
  );
}

export function toCustomerSseEvent(
  event: ConversationPublicEvent,
  correlationId: string,
): Record<string, unknown> {
  const base = {
    correlationId,
    eventId: event.eventId,
    occurredAt: event.occurredAt.toISOString(),
    schemaVersion: event.schemaVersion,
    sequence: event.sequence,
    sessionId: event.sessionId,
    type: event.type,
  };
  if (event.type === 'message.accepted') {
    const { turnId, ...data } = event.payload;
    return { ...base, data, turnId };
  }
  if (event.type === 'turn.processing') {
    return { ...base, data: {}, turnId: event.payload.turnId };
  }
  if (event.type === 'turn.completed') {
    const { turnId, ...payload } = event.payload;
    const data =
      payload.outcome === 'clarification_required'
        ? { citations: [], message: payload.message, outcome: 'conversational' }
        : payload.outcome === 'refused'
          ? { citations: [], ...payload }
          : {
              ...payload,
              citations: payload.citations.map((citation) => ({
                ...citation,
                retrievedAt: citation.retrievedAt.toISOString(),
              })),
            };
    return { ...base, data, turnId };
  }
  if (event.type === 'turn.cancelled') {
    const { turnId, ...data } = event.payload;
    return { ...base, data, turnId };
  }
  if (event.type === 'handoff.requested') {
    const { turnId, ...data } = event.payload;
    return { ...base, data, ...(turnId === undefined ? {} : { turnId }) };
  }
  return { ...base, data: {} };
}

function controlSseFrame(input: {
  readonly correlationId: string;
  readonly data: Record<string, unknown>;
  readonly sessionId: string;
  readonly type:
    'heartbeat' | 'stream.reconnect_required' | 'stream.resync_required';
}): Record<string, unknown> {
  return {
    correlationId: input.correlationId,
    data: input.data,
    occurredAt: new Date().toISOString(),
    schemaVersion: 1,
    sessionId: input.sessionId,
    type: input.type,
  };
}

function requestCorrelationId(request: FastifyRequest): string {
  const value = request.headers['x-correlation-id'];
  return typeof value === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u.test(
      value,
    )
    ? value
    : randomUUID();
}
