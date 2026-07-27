import { randomUUID } from 'node:crypto';
import {
  Injectable,
  Logger,
  type OnModuleDestroy,
  type OnModuleInit,
} from '@nestjs/common';
import { InternalAiTrustConfig } from '../../../../platform/config/internal-ai-trust.config';
import {
  ConversationAiTransport,
  ConversationAiTransportError,
} from '../../application/runtime/conversation-ai.transport';
import {
  ConversationRuntimeClock,
  ConversationRuntimeRepository,
  type ConversationDispatchCandidate,
} from '../../application/runtime/conversation-runtime.repository';
import { ConversationRuntimeService } from '../../application/runtime/conversation-runtime.service';
import { ExecuteConversationTurnService } from '../../application/runtime/execute-conversation-turn.service';

const DISPATCH_INTERVAL_MS = 250;
const DISPATCH_BATCH_SIZE = 12;
const MAX_LOCAL_CONCURRENCY = 3;
const TURN_LEASE_MS = 30_000;
const MIN_CANCELLATION_LEASE_MS = 20_000;
const MAX_CANCELLATION_ATTEMPTS = 5;
const MAX_TURN_DISPATCH_ATTEMPTS = 3;

/**
 * Polls the PostgreSQL-backed conversation inbox. Database OCC and fencing are
 * the cross-instance authority; the local set only avoids duplicate work
 * within this process.
 */
@Injectable()
export class ConversationTurnDispatcher
  implements OnModuleInit, OnModuleDestroy
{
  private readonly logger = new Logger(ConversationTurnDispatcher.name);
  private readonly activeSessions = new Set<string>();
  private cancellationPolling = false;
  private interval: NodeJS.Timeout | null = null;
  private polling = false;
  private readonly workerId = `api-${randomUUID()}`;

  constructor(
    private readonly config: InternalAiTrustConfig,
    private readonly transport: ConversationAiTransport,
    private readonly repository: ConversationRuntimeRepository,
    private readonly runtime: ConversationRuntimeService,
    private readonly executor: ExecuteConversationTurnService,
    private readonly clock: ConversationRuntimeClock,
  ) {}

  onModuleInit(): void {
    if (!this.config.dispatchEnabled) return;
    this.interval = setInterval(
      () => void this.poll().catch((error) => this.logFailure('poll', error)),
      DISPATCH_INTERVAL_MS,
    );
    this.interval.unref();
    void this.poll().catch((error) => this.logFailure('initial-poll', error));
  }

  onModuleDestroy(): void {
    if (this.interval !== null) clearInterval(this.interval);
    this.interval = null;
  }

  kick(): void {
    if (this.config.dispatchEnabled) {
      void this.poll().catch((error) => this.logFailure('kick', error));
    }
  }

  isEnabled(): boolean {
    return this.config.dispatchEnabled;
  }

  private async poll(): Promise<void> {
    if (this.polling || !this.config.dispatchEnabled) {
      return;
    }
    this.polling = true;
    try {
      void this.dispatchCancellations().catch((error) =>
        this.logFailure('cancellation-poll', error),
      );
      if (this.activeSessions.size >= MAX_LOCAL_CONCURRENCY) return;
      const candidates = await this.repository.findDispatchCandidates(
        new Date(),
        DISPATCH_BATCH_SIZE,
      );
      for (const candidate of candidates) {
        if (this.activeSessions.size >= MAX_LOCAL_CONCURRENCY) break;
        if (this.activeSessions.has(candidate.sessionId)) continue;
        this.activeSessions.add(candidate.sessionId);
        void this.dispatch(candidate)
          .catch((error) =>
            this.logFailure('turn-dispatch', error, {
              sessionId: candidate.sessionId,
              turnId: candidate.turnId,
            }),
          )
          .finally(() => {
            this.activeSessions.delete(candidate.sessionId);
            this.kick();
          });
      }
    } finally {
      this.polling = false;
    }
  }

  private async dispatchCancellations(): Promise<void> {
    if (this.cancellationPolling) return;
    this.cancellationPolling = true;
    const now = new Date();
    try {
      const leaseMilliseconds = Math.max(
        MIN_CANCELLATION_LEASE_MS,
        this.config.requestTimeoutMs + 5_000,
      );
      const dispatches = await this.repository.claimCancellationDispatches(
        now,
        new Date(now.getTime() + leaseMilliseconds),
        MAX_LOCAL_CONCURRENCY,
      );
      await Promise.all(
        dispatches.map(async (dispatch) => {
          try {
            await this.transport.cancel(dispatch);
            await this.repository.completeCancellationDispatch(
              dispatch.dispatchId,
            );
          } catch {
            const terminal = dispatch.attempts >= MAX_CANCELLATION_ATTEMPTS;
            const delay = Math.min(
              30_000,
              250 * 2 ** Math.max(0, dispatch.attempts - 1),
            );
            await this.repository.retryCancellationDispatch(
              dispatch.dispatchId,
              new Date(Date.now() + delay),
              terminal,
            );
          }
        }),
      );
    } finally {
      this.cancellationPolling = false;
    }
  }

  private async dispatch(candidate: ConversationDispatchCandidate) {
    const claimed = await this.runtime.claimTurn({
      accessScope: candidate.accessScope,
      expectedVersion: candidate.expectedVersion,
      fencingToken: candidate.nextFencingToken,
      leaseExpiresAt: new Date(Date.now() + TURN_LEASE_MS),
      sessionId: candidate.sessionId,
      turnId: candidate.turnId,
      workerId: this.workerId,
    });
    const correlationId = randomUUID();
    try {
      await this.executor.execute({
        accessScope: candidate.accessScope,
        correlationId,
        deadlineAt: new Date(Date.now() + this.config.requestTimeoutMs),
        requestId: randomUUID(),
        sessionId: candidate.sessionId,
        turnId: candidate.turnId,
      });
    } catch (error) {
      this.logFailure('turn-execution', error, {
        sessionId: candidate.sessionId,
        turnId: candidate.turnId,
      });
      const disposition = classifyTurnFailure(error);
      const terminalAttempt =
        candidate.attempts + 1 >= MAX_TURN_DISPATCH_ATTEMPTS;
      if (disposition === 'retry' && !terminalAttempt) {
        const delay = Math.min(
          30_000,
          250 * 2 ** Math.max(0, candidate.attempts),
        );
        await this.repository.recordTurnDispatchFailure({
          correlationId,
          failureCode: failureCode(error),
          fencingToken: claimed.fencingToken,
          nextAttemptAt: new Date(this.clock.now().getTime() + delay),
          sessionId: candidate.sessionId,
          terminal: false,
          turnId: candidate.turnId,
        });
        return;
      }
      if (disposition === 'stale') return;
      const deadLettered =
        disposition === 'dead-letter' ||
        (disposition === 'retry' && terminalAttempt);
      if (deadLettered) {
        const recorded = await this.repository.recordTurnDispatchFailure({
          correlationId,
          failureCode: failureCode(error),
          fencingToken: claimed.fencingToken,
          nextAttemptAt: this.clock.now(),
          sessionId: candidate.sessionId,
          terminal: true,
          turnId: candidate.turnId,
        });
        if (!recorded) return;
      }
      const context = await this.repository.getTurnExecutionContext(
        candidate.sessionId,
        candidate.accessScope,
        candidate.turnId,
        this.clock.now(),
      );
      if (context === null || context.fencingToken !== claimed.fencingToken) {
        return;
      }
      await this.runtime.completeTurn({
        accessScope: candidate.accessScope,
        expectedVersion: context.conversationVersion,
        fencingToken: context.fencingToken,
        outcome: {
          kind: 'refusal',
          message:
            'Hệ thống trợ lý đang tạm thời gián đoạn. Vui lòng thử lại sau.',
        },
        sessionId: candidate.sessionId,
        turnId: candidate.turnId,
        usage: {
          costMicros: 0,
          modelTokens: 0,
        },
      });
    }
  }

  private logFailure(
    operation: string,
    error: unknown,
    context: Record<string, string> = {},
  ): void {
    this.logger.error({
      ...context,
      error: error instanceof Error ? error.message : String(error),
      operation,
      workerId: this.workerId,
    });
  }
}

type TurnFailureDisposition = 'dead-letter' | 'refuse' | 'retry' | 'stale';

function classifyTurnFailure(error: unknown): TurnFailureDisposition {
  if (!(error instanceof ConversationAiTransportError)) return 'dead-letter';
  if (error.code === 'cancelled' || error.code === 'stale_execution') {
    return 'stale';
  }
  if (error.code === 'policy_denied') return 'refuse';
  return error.retryable ? 'retry' : 'dead-letter';
}

function failureCode(error: unknown): string {
  return error instanceof ConversationAiTransportError
    ? error.code
    : 'unclassified_execution_failure';
}
