import {
  shouldCloseSlowConsumer,
  watchConversationEvents,
} from './conversation-event-stream';
import {
  ConversationEventReplayRequiredError,
  type ConversationRuntimeService,
} from '../application/runtime/conversation-runtime.service';
import type {
  ConversationAccessScope,
  ConversationPublicEvent,
} from '../domain/runtime/conversation-runtime';
import type { ConversationEventReplayBuffer } from '../application/ports/conversation-event-replay-buffer';

const accessScope: ConversationAccessScope = {
  capabilityHash: 'a'.repeat(64),
  kind: 'public_capability',
  profile: 'public_customer',
};

function event(sequence: number): ConversationPublicEvent {
  return {
    cursor: `event-v1:${sequence}`,
    eventId: `event-${sequence}`,
    occurredAt: new Date('2026-07-27T00:00:00.000Z'),
    payload: { turnId: 'turn-1' },
    schemaVersion: 1,
    sequence,
    sessionId: 'session-1',
    type: 'turn.processing',
  };
}

function fakeRuntime(
  pagesByCursor: ReadonlyMap<string, readonly ConversationPublicEvent[]>,
) {
  const listPublicEvents = jest.fn(
    ({ afterCursor }: { afterCursor: string | null }) => {
      const events = pagesByCursor.get(afterCursor ?? 'null') ?? [];
      return Promise.resolve({
        events,
        nextCursor: events.at(-1)?.cursor ?? afterCursor,
      });
    },
  );
  return {
    listPublicEvents,
    runtime: {
      listPublicEvents,
    } as unknown as ConversationRuntimeService,
  };
}

describe('watchConversationEvents', () => {
  it('closes only after the bounded socket buffer limit is exceeded', () => {
    expect(shouldCloseSlowConsumer(65_536, 65_536)).toBe(false);
    expect(shouldCloseSlowConsumer(65_537, 65_536)).toBe(true);
  });

  it('replays everything after the given cursor before polling for more', async () => {
    const { runtime } = fakeRuntime(
      new Map([
        ['null', [event(1), event(2)]],
        ['event-v1:2', []],
      ]),
    );
    const controller = new AbortController();

    const seen: string[] = [];
    for await (const seenEvent of watchConversationEvents(runtime, {
      accessScope,
      afterCursor: null,
      pollIntervalMs: 1,
      sessionId: 'session-1',
      signal: controller.signal,
    })) {
      if (seenEvent.kind === 'event') seen.push(seenEvent.event.cursor);
      if (seen.length === 2) controller.abort();
    }

    expect(seen).toEqual(['event-v1:1', 'event-v1:2']);
  });

  it('advances the cursor across polls so nothing replays twice', async () => {
    const { runtime } = fakeRuntime(
      new Map([
        ['null', [event(1)]],
        ['event-v1:1', [event(2)]],
        ['event-v1:2', []],
      ]),
    );
    const controller = new AbortController();

    const seen: string[] = [];
    for await (const seenEvent of watchConversationEvents(runtime, {
      accessScope,
      afterCursor: null,
      pollIntervalMs: 1,
      sessionId: 'session-1',
      signal: controller.signal,
    })) {
      if (seenEvent.kind === 'event') seen.push(seenEvent.event.cursor);
      if (seen.length === 2) controller.abort();
    }

    expect(seen).toEqual(['event-v1:1', 'event-v1:2']);
  });

  it('resumes from a caller-supplied Last-Event-ID cursor', async () => {
    const { runtime } = fakeRuntime(
      new Map([
        ['event-v1:5', [event(6)]],
        ['event-v1:6', []],
      ]),
    );
    const controller = new AbortController();

    const seen: string[] = [];
    for await (const seenEvent of watchConversationEvents(runtime, {
      accessScope,
      afterCursor: 'event-v1:5',
      pollIntervalMs: 1,
      sessionId: 'session-1',
      signal: controller.signal,
    })) {
      if (seenEvent.kind === 'event') seen.push(seenEvent.event.cursor);
      controller.abort();
    }

    expect(seen).toEqual(['event-v1:6']);
  });

  it('uses the short-lived replay buffer before polling the durable log', async () => {
    const { listPublicEvents, runtime } = fakeRuntime(
      new Map([['event-v1:6', []]]),
    );
    const readAfter = jest.fn(() => Promise.resolve([event(6)]));
    const replayBuffer = {
      append: jest.fn(() => Promise.resolve()),
      readAfter,
    } as ConversationEventReplayBuffer;
    const controller = new AbortController();

    const seen: string[] = [];
    for await (const seenEvent of watchConversationEvents(runtime, {
      accessScope,
      afterCursor: 'event-v1:5',
      pollIntervalMs: 1,
      replayBuffer,
      sessionId: 'session-1',
      signal: controller.signal,
    })) {
      if (seenEvent.kind === 'event') seen.push(seenEvent.event.cursor);
      controller.abort();
    }

    expect(seen).toEqual(['event-v1:6']);
    expect(readAfter).toHaveBeenCalledWith('session-1', 'event-v1:5');
    expect(listPublicEvents).not.toHaveBeenCalled();
  });

  it('stops polling once aborted and never yields again', async () => {
    const { listPublicEvents, runtime } = fakeRuntime(new Map([['null', []]]));
    const controller = new AbortController();
    controller.abort();

    const seen: unknown[] = [];
    for await (const seenEvent of watchConversationEvents(runtime, {
      accessScope,
      afterCursor: null,
      pollIntervalMs: 1,
      sessionId: 'session-1',
      signal: controller.signal,
    })) {
      seen.push(seenEvent);
    }

    expect(seen).toEqual([]);
    expect(listPublicEvents).not.toHaveBeenCalled();
  });

  it('emits one typed resync instruction and closes on an expired cursor', async () => {
    const retentionUntil = new Date('2026-07-28T00:00:00.000Z');
    const runtime = {
      listPublicEvents: jest.fn(() =>
        Promise.reject(
          new ConversationEventReplayRequiredError(
            'cursor_expired',
            'event-v1:51',
            'event-v1:100',
            retentionUntil,
          ),
        ),
      ),
    } as unknown as ConversationRuntimeService;
    const controller = new AbortController();
    const seen = [];

    for await (const item of watchConversationEvents(runtime, {
      accessScope,
      afterCursor: 'event-v1:1',
      pollIntervalMs: 1,
      sessionId: 'session-1',
      signal: controller.signal,
    })) {
      seen.push(item);
    }

    expect(seen).toEqual([
      {
        data: {
          earliestAvailableCursor: 'event-v1:51',
          latestAvailableCursor: 'event-v1:100',
          reason: 'cursor_expired',
          recovery: 'fetch_session_messages_and_handoff_snapshot',
          retentionUntil: retentionUntil.toISOString(),
        },
        kind: 'control',
        type: 'stream.resync_required',
      },
    ]);
  });
});
