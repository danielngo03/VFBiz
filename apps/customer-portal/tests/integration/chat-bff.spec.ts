import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/platform/api/customer-api", () => ({
  customerChatApiRequest: vi.fn(),
  customerChatEventStreamRequest: vi.fn(),
}));
vi.mock("@/platform/session/current-session", () => ({
  currentCustomerSession: vi.fn(),
}));
vi.mock("@/platform/session/request-security", () => ({
  hasValidCsrfToken: vi.fn(),
  hasValidRequestOrigin: vi.fn(),
}));

import {
  customerChatApiRequest,
  customerChatEventStreamRequest,
} from "@/platform/api/customer-api";
import {
  forwardChatEventStream,
  forwardChatMutation,
  forwardChatRead,
  requireUuidV4,
} from "@/features/chat/server/chat-bff";
import { currentCustomerSession } from "@/platform/session/current-session";
import {
  hasValidCsrfToken,
  hasValidRequestOrigin,
} from "@/platform/session/request-security";

const SESSION_ID = "018f47a2-4e68-4c2b-8c23-4c6da5903a41";

function mutationRequest(body: unknown = { locale: "vi" }): Request {
  return new Request("http://localhost:3001/bff/chat/sessions", {
    body: JSON.stringify(body),
    headers: {
      "content-type": "application/json",
      origin: "http://localhost:3001",
      "x-csrf-token": "memory-only-csrf",
    },
    method: "POST",
  });
}

function commandRequest(headers: Record<string, string>): Request {
  return new Request("http://localhost:3001/bff/chat/command", {
    body: "{}",
    headers: {
      "content-type": "application/json",
      origin: "http://localhost:3001",
      "x-csrf-token": "memory-only-csrf",
      ...headers,
    },
    method: "POST",
  });
}

describe("Customer Chat BFF", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(hasValidRequestOrigin).mockReturnValue(true);
    vi.mocked(hasValidCsrfToken).mockReturnValue(true);
    vi.mocked(currentCustomerSession).mockResolvedValue({
      record: { session: {} },
    } as never);
    vi.mocked(customerChatApiRequest).mockResolvedValue(
      Response.json(
        { id: SESSION_ID },
        { headers: { "x-correlation-id": "correlation-1" }, status: 201 },
      ),
    );
    vi.mocked(customerChatEventStreamRequest).mockResolvedValue(
      new Response("event: heartbeat\ndata: {}\n\n", {
        headers: { "content-type": "text/event-stream" },
      }),
    );
  });

  it("forwards a bounded authenticated mutation and hardens the response", async () => {
    const response = await forwardChatMutation(
      mutationRequest(),
      "/api/v1/chat/sessions",
    );

    expect(response.status).toBe(201);
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(response.headers.get("x-correlation-id")).toBe("correlation-1");
    expect(customerChatApiRequest).toHaveBeenCalledWith(
      "/api/v1/chat/sessions",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("forwards only contract-bound concurrency and idempotency headers", async () => {
    const request = commandRequest({
      "if-match": '\"conversation-7\"',
      "idempotency-key": "018f47a2-4e68-4c2b-8c23-4c6da5903a41",
      "x-provider-debug": "forbidden",
    });

    expect(
      (await forwardChatMutation(
        request,
        `/api/v1/chat/sessions/${SESSION_ID}/close`,
      )).status,
    ).toBe(201);
    const init = vi.mocked(customerChatApiRequest).mock.calls[0]?.[1];
    const forwarded = new Headers(init?.headers);
    expect(forwarded.get("if-match")).toBe('\"conversation-7\"');
    expect(forwarded.get("idempotency-key")).toBe(
      "018f47a2-4e68-4c2b-8c23-4c6da5903a41",
    );
    expect(forwarded.get("x-provider-debug")).toBeNull();
  });

  it.each([
    ["if-match", '\"other-7\"'],
    ["idempotency-key", "short"],
  ])("rejects invalid %s before upstream", async (header, value) => {
    const response = await forwardChatMutation(
      commandRequest({ [header]: value }),
      `/api/v1/chat/sessions/${SESSION_ID}/close`,
    );
    expect(response.status).toBe(400);
    expect(customerChatApiRequest).not.toHaveBeenCalled();
  });

  it.each([
    ["origin", 403],
    ["session", 401],
    ["csrf", 403],
  ] as const)("rejects missing %s authority", async (authority, status) => {
    if (authority === "origin") vi.mocked(hasValidRequestOrigin).mockReturnValue(false);
    if (authority === "session") vi.mocked(currentCustomerSession).mockResolvedValue(null);
    if (authority === "csrf") vi.mocked(hasValidCsrfToken).mockReturnValue(false);

    const response = await forwardChatMutation(
      mutationRequest(),
      "/api/v1/chat/sessions",
    );

    expect(response.status).toBe(status);
    expect(customerChatApiRequest).not.toHaveBeenCalled();
  });

  it("rejects malformed, array and over-sized JSON before upstream", async () => {
    const malformed = new Request("http://localhost:3001/bff/chat/sessions", {
      body: "{",
      headers: { "content-type": "application/json" },
      method: "POST",
    });
    const array = mutationRequest([]);
    const oversized = mutationRequest({ content: "x".repeat(17 * 1024) });

    expect(
      (await forwardChatMutation(malformed, "/api/v1/chat/sessions")).status,
    ).toBe(400);
    expect(
      (await forwardChatMutation(array, "/api/v1/chat/sessions")).status,
    ).toBe(400);
    expect(
      (await forwardChatMutation(oversized, "/api/v1/chat/sessions")).status,
    ).toBe(400);
    expect(customerChatApiRequest).not.toHaveBeenCalled();
  });

  it("cancels a length-less streaming body at the byte cap", async () => {
    const encoder = new TextEncoder();
    let cancelled = false;
    const stream = new ReadableStream<Uint8Array>({
      cancel() {
        cancelled = true;
      },
      start(controller) {
        controller.enqueue(encoder.encode('{"content":"'));
        controller.enqueue(encoder.encode("x".repeat(17 * 1024)));
        controller.enqueue(encoder.encode('"}'));
        controller.close();
      },
    });
    const request = new Request(
      "http://localhost:3001/bff/chat/sessions",
      {
        body: stream,
        headers: { "content-type": "application/json" },
        method: "POST",
        duplex: "half",
      } as RequestInit & { duplex: "half" },
    );

    const response = await forwardChatMutation(
      request,
      "/api/v1/chat/sessions",
    );

    expect(response.status).toBe(400);
    expect(cancelled).toBe(true);
    expect(customerChatApiRequest).not.toHaveBeenCalled();
  });

  it("streams an upstream read without exposing provider headers", async () => {
    vi.mocked(customerChatEventStreamRequest).mockResolvedValue(
      new Response("event: heartbeat\ndata: {}\n\n", {
        headers: {
          authorization: "forbidden",
          "content-type": "text/event-stream",
          "x-correlation-id": "correlation-stream",
        },
      }),
    );

    const downstream = new AbortController();
    const request = new Request("http://localhost:3001/bff/chat/events", {
      signal: downstream.signal,
    });
    const response = await forwardChatEventStream(
      request,
      `/api/v1/chat/sessions/${SESSION_ID}/events`,
      "cursor-1",
    );

    expect(response.headers.get("content-type")).toBe("text/event-stream");
    expect(response.headers.get("x-accel-buffering")).toBe("no");
    expect(response.headers.get("authorization")).toBeNull();
    expect(response.headers.get("x-correlation-id")).toBe("correlation-stream");
    expect(await response.text()).toContain("heartbeat");
    expect(customerChatEventStreamRequest).toHaveBeenCalledWith(
      `/api/v1/chat/sessions/${SESSION_ID}/events`,
      request.signal,
      "cursor-1",
    );
  });

  it("maps upstream failures without returning raw provider payload", async () => {
    vi.mocked(customerChatApiRequest).mockRejectedValue(
      new Error("secret provider detail"),
    );

    const response = await forwardChatRead(
      `/api/v1/chat/sessions/${SESSION_ID}`,
    );

    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("secret provider detail");
  });

  it("redacts an upstream HTTP 5xx body while preserving correlation", async () => {
    vi.mocked(customerChatApiRequest).mockResolvedValue(
      Response.json(
        { internal: "provider stack and credential detail" },
        { headers: { "x-correlation-id": "safe-correlation" }, status: 502 },
      ),
    );

    const response = await forwardChatRead(
      `/api/v1/chat/sessions/${SESSION_ID}`,
    );
    const body = await response.text();

    expect(response.status).toBe(503);
    expect(response.headers.get("x-correlation-id")).toBe("safe-correlation");
    expect(body).not.toContain("provider stack");
    expect(body).toContain("chat_unavailable");
  });

  it("accepts only canonical UUID v4 resource identifiers", () => {
    expect(requireUuidV4(SESSION_ID)).toBe(SESSION_ID);
    expect(() => requireUuidV4("../other-subject")).toThrow(
      "Invalid Chat resource identity",
    );
    expect(() => requireUuidV4(SESSION_ID.toUpperCase())).toThrow();
  });
});
