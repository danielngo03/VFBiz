import assert from "node:assert/strict";
import test from "node:test";
import { SseParser } from "../../src/features/chat/model/sse-parser.ts";

test("SSE parser preserves split frames and durable cursor", () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push('id: cursor-1\ndata: {"type":"turn.'), []);
  assert.deepEqual(parser.push('completed"}\n\n'), [
    { id: "cursor-1", data: '{"type":"turn.completed"}' },
  ]);
});

test("SSE parser retains an explicit control-event type", () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push('event: stream.resync_required\ndata: {"reason":"cursor_expired"}\n\n'), [
    { event: "stream.resync_required", data: '{"reason":"cursor_expired"}' },
  ]);
});

test("SSE parser ignores comments and joins multiline data", () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push(": heartbeat\n\nid: c2\ndata: first\ndata: second\n\n"), [
    { id: "c2", data: "first\nsecond" },
  ]);
});

test("SSE parser normalizes CRLF split across network chunks", () => {
  const parser = new SseParser();
  assert.deepEqual(parser.push("id: c3\r"), []);
  assert.deepEqual(parser.push("\ndata: ok\r\n\r\n"), [
    { id: "c3", data: "ok" },
  ]);
});
