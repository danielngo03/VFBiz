import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/platform/auth/oidc", () => ({ refreshTokens: vi.fn() }));
vi.mock("@/platform/config/environment", () => ({
  readCustomerPortalEnvironment: vi.fn(() => ({
    CUSTOMER_API_BASE_URL: "https://api.internal.example",
  })),
}));
vi.mock("@/platform/session/current-session", () => ({
  currentCustomerSession: vi.fn(),
}));
vi.mock("@/platform/session/redis-token-vault", () => ({
  acquireRefreshLease: vi.fn(),
  deleteSession: vi.fn(),
  readSession: vi.fn(),
  releaseRefreshLease: vi.fn(),
  writeSession: vi.fn(),
}));

import {
  customerChatApiRequest,
  customerChatEventStreamRequest,
} from "@/platform/api/customer-api";
import { currentCustomerSession } from "@/platform/session/current-session";

const SESSION_ID = "018f47a2-4e68-4c2b-8c23-4c6da5903a41";

describe("Customer Chat server-only API transport", () => {
  beforeEach(() => {
    vi.mocked(currentCustomerSession).mockResolvedValue({
      record: {
        tokenSet: {
          accessToken: "internal-only-token",
          expiresAt: new Date(Date.now() + 60_000),
        },
      },
    } as never);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetAllMocks();
  });

  it("ties the SSE upstream lifecycle to downstream abort and keeps bearer server-side", async () => {
    let observed: RequestInit | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: URL, init?: RequestInit) => {
        observed = init;
        return new Response("event: heartbeat\ndata: {}\n\n", {
          headers: { "content-type": "text/event-stream" },
        });
      }),
    );
    const downstream = new AbortController();

    await customerChatEventStreamRequest(
      `/api/v1/chat/sessions/${SESSION_ID}/events`,
      downstream.signal,
      "cursor-1",
    );

    const headers = new Headers(observed?.headers);
    expect(headers.get("authorization")).toBe("Bearer internal-only-token");
    expect(headers.get("accept")).toBe("text/event-stream");
    expect(headers.get("last-event-id")).toBe("cursor-1");
    expect(observed?.credentials).toBe("omit");
    expect(observed?.signal?.aborted).toBe(false);
    downstream.abort();
    expect(observed?.signal?.aborted).toBe(true);
  });

  it("rejects every path outside the reviewed Chat resource boundary", async () => {
    expect(() =>
      customerChatEventStreamRequest(
        "/api/v1/me",
        new AbortController().signal,
      ),
    ).toThrow("outside the reviewed boundary");
    await expect(
      customerChatApiRequest("/api/v1/chat/sessions/../other-subject", {
        method: "GET",
      }),
    ).rejects.toThrow("outside the reviewed boundary");
  });
});
