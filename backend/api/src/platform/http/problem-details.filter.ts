import {
  ArgumentsHost,
  Catch,
  ExceptionFilter,
  HttpException,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import type { FastifyReply } from 'fastify';
import { requestCorrelationId, RequestWithContext } from './request-context';

interface ExceptionBody {
  code?: string;
  message?: string | string[];
}

interface TypedConversationProblem {
  readonly status: number;
  readonly code: string;
}

const TYPED_CONVERSATION_PROBLEMS: Readonly<
  Record<string, TypedConversationProblem>
> = {
  ConversationBudgetExceededError: {
    status: HttpStatus.TOO_MANY_REQUESTS,
    code: 'CHAT_BUDGET_EXHAUSTED',
  },
  ConversationBudgetValidationError: {
    status: HttpStatus.BAD_REQUEST,
    code: 'CHAT_BUDGET_INVALID',
  },
  ConversationCursorValidationError: {
    status: HttpStatus.BAD_REQUEST,
    code: 'CHAT_CURSOR_INVALID',
  },
  ConversationEventReplayRequiredError: {
    status: HttpStatus.CONFLICT,
    code: 'CHAT_EVENT_REPLAY_REQUIRED',
  },
  ConversationInputValidationError: {
    status: HttpStatus.BAD_REQUEST,
    code: 'CHAT_INPUT_INVALID',
  },
  ConversationInvalidTransitionError: {
    status: HttpStatus.CONFLICT,
    code: 'CHAT_STATE_CONFLICT',
  },
  ConversationMessageIdempotencyConflictError: {
    status: HttpStatus.CONFLICT,
    code: 'CHAT_IDEMPOTENCY_CONFLICT',
  },
  ConversationRuntimeNotFoundError: {
    status: HttpStatus.NOT_FOUND,
    code: 'CHAT_SESSION_NOT_FOUND',
  },
  ConversationStaleFencingTokenError: {
    status: HttpStatus.CONFLICT,
    code: 'CHAT_STALE_FENCE',
  },
  ConversationTaskConflictError: {
    status: HttpStatus.CONFLICT,
    code: 'CHAT_TASK_CONFLICT',
  },
  ConversationTurnNotFoundError: {
    status: HttpStatus.NOT_FOUND,
    code: 'CHAT_TURN_NOT_FOUND',
  },
  ConversationVersionConflictError: {
    status: HttpStatus.CONFLICT,
    code: 'CHAT_VERSION_CONFLICT',
  },
};

const TITLES: Partial<Record<number, string>> = {
  [HttpStatus.BAD_REQUEST]: 'Bad Request',
  [HttpStatus.UNAUTHORIZED]: 'Unauthorized',
  [HttpStatus.FORBIDDEN]: 'Forbidden',
  [HttpStatus.NOT_FOUND]: 'Not Found',
  [HttpStatus.CONFLICT]: 'Conflict',
  [HttpStatus.TOO_MANY_REQUESTS]: 'Too Many Requests',
  [HttpStatus.INTERNAL_SERVER_ERROR]: 'Internal Server Error',
};

@Catch()
export class ProblemDetailsFilter implements ExceptionFilter {
  private readonly logger = new Logger(ProblemDetailsFilter.name);

  catch(exception: unknown, host: ArgumentsHost): void {
    const context = host.switchToHttp();
    const request = context.getRequest<RequestWithContext>();
    const reply = context.getResponse<FastifyReply>();
    const typed = this.typedConversationProblem(exception);
    const status =
      exception instanceof HttpException
        ? exception.getStatus()
        : (typed?.status ?? HttpStatus.INTERNAL_SERVER_ERROR);
    const body = this.exceptionBody(exception);
    const code = body.code ?? typed?.code ?? this.defaultCode(status);
    const detail =
      status === 500
        ? 'The service could not complete the request.'
        : this.detail(body, exception);
    if (status === 500) {
      this.logger.error({
        correlationId: requestCorrelationId(request),
        event: 'unhandled-request-exception',
        exceptionName:
          exception instanceof Error ? exception.name : 'NonErrorException',
        message:
          process.env.NODE_ENV === 'production' || !(exception instanceof Error)
            ? undefined
            : exception.message,
      });
    }

    reply
      .status(status)
      .type('application/problem+json')
      .send({
        type: `https://vfbiz.vn/problems/${code.toLowerCase().replaceAll('_', '-')}`,
        title: TITLES[status] ?? 'Request Failed',
        status,
        detail,
        instance: request.url,
        code,
        correlationId: requestCorrelationId(request),
      });
  }

  private typedConversationProblem(
    exception: unknown,
  ): TypedConversationProblem | undefined {
    if (!(exception instanceof Error)) return undefined;
    return TYPED_CONVERSATION_PROBLEMS[exception.name];
  }

  private exceptionBody(exception: unknown): ExceptionBody {
    if (!(exception instanceof HttpException)) return {};
    const response = exception.getResponse();
    if (typeof response === 'string') return { message: response };
    return response;
  }

  private detail(body: ExceptionBody, exception: unknown): string {
    if (Array.isArray(body.message)) return body.message.join('; ');
    if (typeof body.message === 'string') return body.message;
    if (exception instanceof HttpException) return exception.message;
    return 'Request failed.';
  }

  private defaultCode(status: number): string {
    return (
      (
        {
          [HttpStatus.BAD_REQUEST]: 'BAD_REQUEST',
          [HttpStatus.UNAUTHORIZED]: 'UNAUTHORIZED',
          [HttpStatus.FORBIDDEN]: 'FORBIDDEN',
          [HttpStatus.NOT_FOUND]: 'NOT_FOUND',
          [HttpStatus.CONFLICT]: 'CONFLICT',
          [HttpStatus.TOO_MANY_REQUESTS]: 'RATE_LIMITED',
        } as Record<number, string>
      )[status] ?? 'INTERNAL_ERROR'
    );
  }
}
