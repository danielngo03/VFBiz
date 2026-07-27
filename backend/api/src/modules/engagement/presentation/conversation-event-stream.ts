import type { ConversationAccessScope } from '../domain/runtime/conversation-runtime';
import type { ConversationPublicEvent } from '../domain/runtime/conversation-runtime';
import type { ConversationRuntimeService } from '../application/runtime/conversation-runtime.service';
import { ConversationEventReplayRequiredError } from '../application/runtime/conversation-runtime.service';
import type { ConversationEventReplayBuffer } from '../application/ports/conversation-event-replay-buffer';

export type ConversationEventStreamItem =
  | {
      readonly event: ConversationPublicEvent;
      readonly kind: 'event';
    }
  | {
      readonly data: {
        readonly earliestAvailableCursor: string | null;
        readonly latestAvailableCursor: string | null;
        readonly reason:
          'cursor_expired' | 'cursor_out_of_range' | 'retention_expired';
        readonly retentionUntil: string;
        readonly recovery: 'fetch_session_messages_and_handoff_snapshot';
      };
      readonly kind: 'control';
      readonly type: 'stream.resync_required';
    };

export interface WatchConversationEventsInput {
  readonly accessScope: ConversationAccessScope;
  readonly afterCursor: string | null;
  readonly pollIntervalMs: number;
  readonly replayBuffer?: ConversationEventReplayBuffer;
  readonly sessionId: string;
  readonly signal: AbortSignal;
}

/**
 * Adapts the durable, poll-based `listPublicEvents` read into a live stream:
 * replay everything after `afterCursor` first (the Last-Event-ID reconnect
 * case), then keep polling for newly-committed events until aborted. SSE is
 * a projection over this durable store, never the source of truth itself.
 */
export async function* watchConversationEvents(
  runtime: ConversationRuntimeService,
  input: WatchConversationEventsInput,
): AsyncGenerator<ConversationEventStreamItem> {
  let cursor = input.afterCursor;
  if (cursor !== null && input.replayBuffer !== undefined) {
    const replay = await input.replayBuffer.readAfter(input.sessionId, cursor);
    if (replay !== null) {
      for (const event of replay) {
        yield { event, kind: 'event' };
        cursor = event.cursor;
      }
    }
  }
  while (!input.signal.aborted) {
    let page;
    try {
      page = await runtime.listPublicEvents({
        accessScope: input.accessScope,
        afterCursor: cursor,
        sessionId: input.sessionId,
      });
    } catch (error) {
      if (!(error instanceof ConversationEventReplayRequiredError)) throw error;
      yield {
        data: {
          earliestAvailableCursor: error.earliestAvailableCursor,
          latestAvailableCursor: error.latestAvailableCursor,
          reason: error.reason,
          recovery: 'fetch_session_messages_and_handoff_snapshot',
          retentionUntil: error.retentionUntil.toISOString(),
        },
        kind: 'control',
        type: 'stream.resync_required',
      };
      return;
    }
    await input.replayBuffer?.append(input.sessionId, page.events);
    for (const event of page.events) {
      yield { event, kind: 'event' };
      cursor = event.cursor;
    }
    if (input.signal.aborted) return;
    await delay(input.pollIntervalMs, input.signal);
  }
}

export function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const timeout = setTimeout(resolve, ms);
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timeout);
        resolve();
      },
      { once: true },
    );
  });
}

export function shouldCloseSlowConsumer(
  writableLength: number,
  maximumBufferedBytes: number,
): boolean {
  return (
    Number.isSafeInteger(writableLength) &&
    Number.isSafeInteger(maximumBufferedBytes) &&
    maximumBufferedBytes > 0 &&
    writableLength > maximumBufferedBytes
  );
}
