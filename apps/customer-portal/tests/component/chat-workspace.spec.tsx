import axe from "axe-core";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatWorkspace } from "@/features/chat/components/chat-workspace";

describe("authenticated Chat workspace", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("fails closed without exposing a token or a public-chat claim", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json({ csrfToken: "memory-only-csrf-token" }))
      .mockResolvedValueOnce(Response.json({ error: "chat_unavailable" }, { status: 503 }));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<ChatWorkspace />);

    expect(screen.getByText("Authenticated staging")).toBeVisible();
    expect(screen.getByText(/không đại diện cho bản phát hành công khai/iu)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Bắt đầu phiên kiểm thử" }));
    await waitFor(() => expect(screen.getByText("Trợ lý chưa sẵn sàng.")).toBeVisible());
    expect(screen.getByText("Đã khóa")).toBeVisible();
    expect(JSON.stringify(fetchMock.mock.calls)).not.toMatch(/access[_-]?token|bearer/iu);

    const results = await axe.run(container);
    expect(
      results.violations.filter((violation) =>
        ["critical", "serious"].includes(violation.impact ?? ""),
      ),
    ).toEqual([]);
  });

  it("locks the composer when the runtime kill switch trips during a message", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/auth/security") {
        return Response.json({ csrfToken: "memory-only-csrf-token" });
      }
      if (url === "/bff/chat/sessions" && init?.method === "POST") {
        return Response.json(activeSession(), { status: 201 });
      }
      if (url.endsWith("/events")) {
        return new Response(new ReadableStream<Uint8Array>({ start() {} }), {
          headers: { "content-type": "text/event-stream" },
        });
      }
      if (url.endsWith("/messages") && init?.method === "POST") {
        return Response.json({ error: "chat_unavailable" }, { status: 503 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ChatWorkspace />);

    await user.click(screen.getByRole("button", { name: "Bắt đầu phiên kiểm thử" }));
    await screen.findByText("Sẵn sàng", { exact: true });
    await user.type(screen.getByLabelText("Nội dung tin nhắn"), "Thông tin bảo hành?");
    await user.click(screen.getByRole("button", { name: "Gửi", exact: true }));

    await screen.findByText("Đã khóa");
    expect(screen.getByLabelText("Nội dung tin nhắn")).toBeDisabled();
    expect(screen.getByText("Trợ lý đã được khóa an toàn.")).toBeVisible();
  });

  it("requires explicit confirmation before closing and disables duplicate action", async () => {
    const user = userEvent.setup();
    const closeRequests: RequestInit[] = [];
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/auth/security") {
        return Response.json({ csrfToken: "memory-only-csrf-token" });
      }
      if (url === "/bff/chat/sessions" && init?.method === "POST") {
        return Response.json(activeSession(), { status: 201 });
      }
      if (url.endsWith("/events")) {
        return new Response(new ReadableStream<Uint8Array>({ start() {} }), {
          headers: { "content-type": "text/event-stream" },
        });
      }
      if (url.endsWith("/close")) {
        closeRequests.push(init ?? {});
        return Response.json({ ...activeSession(), status: "closed", version: 1 });
      }
      if (url.endsWith("/sessions/018f47a2-4e68-4c2b-8c23-4c6da5903a41")) {
        return Response.json({ ...activeSession(), status: "closed", version: 1 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ChatWorkspace />);

    await user.click(screen.getByRole("button", { name: "Bắt đầu phiên kiểm thử" }));
    await screen.findByText("Sẵn sàng", { exact: true });
    await user.click(screen.getByRole("button", { name: "Đóng phiên" }));
    expect(closeRequests).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Xác nhận đóng phiên" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Xác nhận đóng phiên" }));
    await screen.findByText(/Phiên đã đóng/iu);
    expect(closeRequests).toHaveLength(1);
  });

  it("recovers an expired cursor from durable session and message reads", async () => {
    const user = userEvent.setup();
    const encoder = new TextEncoder();
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/auth/security") {
        return Response.json({ csrfToken: "memory-only-csrf-token" });
      }
      if (url === "/bff/chat/sessions" && init?.method === "POST") {
        return Response.json(activeSession(), { status: 201 });
      }
      if (url.endsWith("/events")) {
        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(
                encoder.encode(
                  'event: stream.resync_required\ndata: {"reason":"cursor_expired"}\n\n',
                ),
              );
              controller.close();
            },
          }),
          { headers: { "content-type": "text/event-stream" } },
        );
      }
      if (url.endsWith("/messages")) {
        return Response.json({ items: [], nextCursor: null });
      }
      if (url.endsWith("/sessions/018f47a2-4e68-4c2b-8c23-4c6da5903a41")) {
        return Response.json(activeSession());
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ChatWorkspace />);

    await user.click(screen.getByRole("button", { name: "Bắt đầu phiên kiểm thử" }));
    await screen.findByText("Luồng cập nhật đã được đồng bộ lại từ dữ liệu bền vững.");
    expect(
      fetchMock.mock.calls.some(([input]) => String(input).endsWith("/messages")),
    ).toBe(true);
  });

  it("clears an HTTP 409 cursor and resynchronizes instead of replaying it", async () => {
    const user = userEvent.setup();
    let eventRequests = 0;
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/auth/security") return Response.json({ csrfToken: "memory-only-csrf-token" });
      if (url === "/bff/chat/sessions" && init?.method === "POST") return Response.json(activeSession(), { status: 201 });
      if (url.endsWith("/events")) {
        eventRequests += 1;
        return eventRequests === 1
          ? Response.json({ code: "STREAM_CURSOR_EXPIRED" }, { status: 409 })
          : new Response(new ReadableStream<Uint8Array>({ start() {} }));
      }
      if (url.endsWith("/messages")) return Response.json({ items: [], nextCursor: null });
      if (url.endsWith("/sessions/018f47a2-4e68-4c2b-8c23-4c6da5903a41")) return Response.json(activeSession());
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ChatWorkspace />);

    await user.click(screen.getByRole("button", { name: "Bắt đầu phiên kiểm thử" }));
    await screen.findByText("Con trỏ cập nhật đã hết hạn; phiên được đồng bộ lại từ dữ liệu bền vững.");
    const eventCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/events"));
    expect(new Headers(eventCall?.[1]?.headers).has("last-event-id")).toBe(false);
  });

  it("locks the UI when durable resynchronization observes a disabled runtime", async () => {
    const user = userEvent.setup();
    const encoder = new TextEncoder();
    const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/auth/security") return Response.json({ csrfToken: "memory-only-csrf-token" });
      if (url === "/bff/chat/sessions" && init?.method === "POST") return Response.json(activeSession(), { status: 201 });
      if (url.endsWith("/events")) {
        return new Response(new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(encoder.encode('event: stream.resync_required\ndata: {"reason":"cursor_expired"}\n\n'));
            controller.close();
          },
        }));
      }
      if (url.endsWith("/messages")) return Response.json({ error: "chat_unavailable" }, { status: 503 });
      if (url.endsWith("/sessions/018f47a2-4e68-4c2b-8c23-4c6da5903a41")) return Response.json(activeSession());
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ChatWorkspace />);

    await user.click(screen.getByRole("button", { name: "Bắt đầu phiên kiểm thử" }));
    await screen.findByText("Đã khóa");
    expect(screen.getByLabelText("Nội dung tin nhắn")).toBeDisabled();
  });
});

function activeSession() {
  return {
    createdAt: "2026-08-01T10:00:00.000Z",
    expiresAt: "2026-08-01T10:30:00.000Z",
    id: "018f47a2-4e68-4c2b-8c23-4c6da5903a41",
    locale: "vi",
    profile: "authenticated_customer",
    retentionUntil: "2026-08-02T10:00:00.000Z",
    status: "active",
    version: 0,
  } as const;
}
