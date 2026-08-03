"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type {
  ConversationEvent,
  ConversationMessage,
  ConversationMessagePage,
  ConversationSession,
  MessageAccepted,
} from "../model/chat-types";
import { SseParser } from "../model/sse-parser";

const CHAT_BUDGET = { maxCostMicros: 50_000, maxModelTokens: 2_048 } as const;

type Activity = "idle" | "connecting" | "ready" | "processing" | "unavailable";

class ChatUnavailableError extends Error {}

export function ChatWorkspace() {
  const [session, setSession] = useState<ConversationSession | null>(null);
  const [messages, setMessages] = useState<readonly ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [activity, setActivity] = useState<Activity>("idle");
  const [notice, setNotice] = useState(
    "Bắt đầu một phiên để kiểm tra trợ lý trong môi trường có kiểm soát.",
  );
  const [activeTurn, setActiveTurn] = useState<string | null>(null);
  const [pendingCommand, setPendingCommand] = useState<
    "cancel" | "handoff" | "close" | null
  >(null);
  const [closeConfirmation, setCloseConfirmation] = useState(false);
  const csrfToken = useRef<string | null>(null);
  const streamAbort = useRef<AbortController | null>(null);
  const commandKeys = useRef<
    Partial<Record<"cancel" | "handoff" | "close", string>>
  >({});
  const pendingMessage = useRef<{
    content: string;
    clientMessageId: string;
  } | null>(null);

  const secureFetch = useCallback(
    async (path: string, init: RequestInit = {}) => {
      if (csrfToken.current === null) {
        const security = await fetch("/api/auth/security", {
          cache: "no-store",
        });
        if (!security.ok)
          throw new Error("Phiên đăng nhập không còn hiệu lực.");
        const body = (await security.json()) as { csrfToken?: unknown };
        if (typeof body.csrfToken !== "string" || body.csrfToken.length < 16) {
          throw new Error("Không thể xác minh phiên bảo mật.");
        }
        csrfToken.current = body.csrfToken;
      }
      const headers = new Headers(init.headers);
      headers.set("content-type", "application/json");
      headers.set("x-csrf-token", csrfToken.current);
      return fetch(path, { ...init, cache: "no-store", headers });
    },
    [],
  );

  const refreshMessages = useCallback(async (sessionId: string) => {
    const response = await fetch(`/bff/chat/sessions/${sessionId}/messages`, {
      cache: "no-store",
    });
    if (response.status === 503)
      throw new ChatUnavailableError("Trợ lý đã được khóa an toàn.");
    if (!response.ok) throw new Error("Không thể đồng bộ lịch sử trò chuyện.");
    const page = (await response.json()) as ConversationMessagePage;
    setMessages(page.items);
  }, []);

  const refreshSession = useCallback(async (sessionId: string) => {
    const response = await fetch(`/bff/chat/sessions/${sessionId}`, {
      cache: "no-store",
    });
    if (response.status === 503)
      throw new ChatUnavailableError("Trợ lý đã được khóa an toàn.");
    if (!response.ok) throw new Error("Không thể đồng bộ trạng thái phiên.");
    const current = (await response.json()) as ConversationSession;
    setSession(current);
    return current;
  }, []);

  const applyEvent = useCallback(
    async (sessionId: string, event: ConversationEvent) => {
      if (
        event.type === "turn.processing" ||
        event.type === "retrieval.started"
      ) {
        setActivity("processing");
        setNotice("Đang kiểm tra nguồn và xây dựng câu trả lời…");
        return;
      }
      if (
        ["turn.completed", "turn.cancelled", "handoff.requested"].includes(
          event.type,
        )
      ) {
        setActiveTurn(null);
        await Promise.all([
          refreshMessages(sessionId),
          refreshSession(sessionId),
        ]);
        setActivity("ready");
        setNotice(
          event.type === "handoff.requested"
            ? "Yêu cầu hỗ trợ đã được ghi nhận."
            : "Phiên đã được đồng bộ.",
        );
      }
    },
    [refreshMessages, refreshSession],
  );

  const connectStream = useCallback(
    async (sessionId: string, initialCursor?: string) => {
      streamAbort.current?.abort();
      const controller = new AbortController();
      streamAbort.current = controller;
      let cursor = initialCursor;
      let retryMs = 500;
      while (!controller.signal.aborted) {
        try {
          const response = await fetch(
            `/bff/chat/sessions/${sessionId}/events`,
            {
              cache: "no-store",
              headers: cursor ? { "last-event-id": cursor } : undefined,
              signal: controller.signal,
            },
          );
          if (response.status === 409) {
            cursor = undefined;
            setActiveTurn(null);
            await Promise.all([
              refreshMessages(sessionId),
              refreshSession(sessionId),
            ]);
            setActivity("ready");
            setNotice(
              "Con trỏ cập nhật đã hết hạn; phiên được đồng bộ lại từ dữ liệu bền vững.",
            );
            await new Promise((resolve) => window.setTimeout(resolve, retryMs));
            continue;
          }
          if (response.status === 503) {
            setActivity("unavailable");
            setNotice(
              "Trợ lý đã được khóa an toàn. Không có yêu cầu mới nào được gửi.",
            );
            return;
          }
          if (!response.ok || response.body === null)
            throw new Error("stream unavailable");
          retryMs = 500;
          const parser = new SseParser();
          const decoder = new TextDecoder();
          const reader = response.body.getReader();
          while (!controller.signal.aborted) {
            const { done, value } = await reader.read();
            if (done) break;
            for (const frame of parser.push(
              decoder.decode(value, { stream: true }),
            )) {
              const payload = JSON.parse(frame.data) as Record<string, unknown>;
              const type =
                typeof payload.type === "string" ? payload.type : frame.event;
              if (type === "stream.resync_required") {
                cursor = undefined;
                setActiveTurn(null);
                await Promise.all([
                  refreshMessages(sessionId),
                  refreshSession(sessionId),
                ]);
                setActivity("ready");
                setNotice(
                  "Luồng cập nhật đã được đồng bộ lại từ dữ liệu bền vững.",
                );
                await reader.cancel("durable resync completed");
                break;
              }
              if (type === "stream.reconnect_required") {
                if (typeof payload.lastEventId === "string")
                  cursor = payload.lastEventId;
                setNotice("Máy chủ yêu cầu nối lại luồng cập nhật an toàn.");
                await reader.cancel("bounded reconnect requested");
                break;
              }
              if (type === undefined) throw new Error("unknown SSE frame");
              const event = {
                ...payload,
                type,
              } as unknown as ConversationEvent;
              await applyEvent(sessionId, event);
              if (frame.id) cursor = frame.id;
            }
          }
        } catch (error) {
          if (controller.signal.aborted) return;
          if (error instanceof ChatUnavailableError) {
            setActivity("unavailable");
            setNotice(error.message);
            return;
          }
          setNotice(
            "Kết nối cập nhật bị gián đoạn; hệ thống đang tự nối lại an toàn.",
          );
        }
        await new Promise((resolve) => window.setTimeout(resolve, retryMs));
        retryMs = Math.min(retryMs * 2, 5_000);
      }
    },
    [applyEvent, refreshMessages, refreshSession],
  );

  useEffect(() => () => streamAbort.current?.abort(), []);

  async function beginSession() {
    setActivity("connecting");
    try {
      const response = await secureFetch("/bff/chat/sessions", {
        body: JSON.stringify({ locale: "vi" }),
        method: "POST",
      });
      if (!response.ok) throw new ChatUnavailableError("Trợ lý chưa sẵn sàng.");
      const created = (await response.json()) as ConversationSession;
      setSession(created);
      setMessages([]);
      setActivity("ready");
      setNotice(
        "Phiên đã sẵn sàng. Câu trả lời có dữ kiện phải kèm nguồn hoặc từ chối an toàn.",
      );
      void connectStream(created.id);
    } catch (error) {
      setActivity("unavailable");
      setNotice(
        error instanceof Error ? error.message : "Trợ lý chưa sẵn sàng.",
      );
    }
  }

  async function sendMessage() {
    const content = draft.trim();
    if (session === null || content.length === 0 || activity === "processing")
      return;
    setActivity("processing");
    setNotice("Tin nhắn đã được gửi an toàn…");
    try {
      const clientMessageId =
        pendingMessage.current?.content === content
          ? pendingMessage.current.clientMessageId
          : crypto.randomUUID();
      pendingMessage.current = { clientMessageId, content };
      const response = await secureFetch(
        `/bff/chat/sessions/${session.id}/messages`,
        {
          body: JSON.stringify({
            budget: CHAT_BUDGET,
            clientMessageId,
            content,
            expectedVersion: session.version,
            kind: "message.enqueue",
          }),
          method: "POST",
        },
      );
      if (response.status === 503)
        throw new ChatUnavailableError("Trợ lý đã được khóa an toàn.");
      if (!response.ok) throw new Error("Tin nhắn chưa được chấp nhận.");
      const accepted = (await response.json()) as MessageAccepted;
      pendingMessage.current = null;
      setDraft("");
      setActiveTurn(accepted.turnId);
      setSession({ ...session, version: accepted.conversationVersion });
      await refreshMessages(session.id);
    } catch (error) {
      setActivity(
        error instanceof ChatUnavailableError ? "unavailable" : "ready",
      );
      setNotice(
        error instanceof Error ? error.message : "Không thể gửi tin nhắn.",
      );
    }
  }

  async function issueCommand(kind: "cancel" | "handoff" | "close") {
    if (session === null) return;
    if (kind === "close" && !closeConfirmation) {
      setCloseConfirmation(true);
      setNotice(
        "Đóng phiên sẽ dừng mọi lượt mới. Chọn “Xác nhận đóng phiên” để tiếp tục.",
      );
      return;
    }
    setPendingCommand(kind);
    const idempotencyKey = commandKeys.current[kind] ?? crypto.randomUUID();
    commandKeys.current[kind] = idempotencyKey;
    const target =
      kind === "cancel" && activeTurn
        ? `/bff/chat/sessions/${session.id}/turns/${activeTurn}/cancel`
        : `/bff/chat/sessions/${session.id}/${kind}`;
    const body =
      kind === "cancel"
        ? {
            expectedVersion: session.version,
            kind: "turn.cancel",
            reason: "user_interrupt",
          }
        : kind === "handoff"
          ? {
              expectedVersion: session.version,
              kind: "handoff.request",
              reason: "customer_requested",
            }
          : { expectedVersion: session.version };
    try {
      const response = await secureFetch(target, {
        body: JSON.stringify(body),
        headers: {
          "idempotency-key": idempotencyKey,
          ...(kind === "close"
            ? { "if-match": `"conversation-${session.version}"` }
            : {}),
        },
        method: "POST",
      });
      if (response.status === 503)
        throw new ChatUnavailableError("Trợ lý đã được khóa an toàn.");
      if (!response.ok) throw new Error("Yêu cầu chưa được chấp nhận.");
      delete commandKeys.current[kind];
      await refreshSession(session.id);
      if (kind === "close") {
        streamAbort.current?.abort();
        setActivity("idle");
        setNotice("Phiên đã đóng; lịch sử được giữ theo chính sách kiểm soát.");
        setCloseConfirmation(false);
      }
    } catch (error) {
      if (error instanceof ChatUnavailableError) setActivity("unavailable");
      setNotice(
        error instanceof Error ? error.message : "Không thể thực hiện yêu cầu.",
      );
    } finally {
      setPendingCommand(null);
    }
  }

  const usable = session?.status === "active" && activity !== "unavailable";
  return (
    <section className="chat-shell" aria-labelledby="chat-title">
      <header className="chat-header">
        <div>
          <p className="eyebrow">Authenticated staging</p>
          <h1 id="chat-title">Trợ lý khách hàng</h1>
          <p>
            Phiên thử nghiệm có đăng nhập, dùng nguồn được kiểm soát và không
            đại diện cho bản phát hành công khai.
          </p>
        </div>
        <span className={`chat-status chat-status-${activity}`}>
          {activityLabel(activity)}
        </span>
      </header>

      <p className="chat-notice" role="status" aria-live="polite">
        {notice}
      </p>

      {session === null ? (
        <div className="chat-empty">
          <h2>Chưa có phiên trò chuyện</h2>
          <p>
            Trình duyệt chỉ giữ mã CSRF trong bộ nhớ. Access token vẫn nằm ở BFF
            phía máy chủ.
          </p>
          <Button
            onClick={() => void beginSession()}
            disabled={activity === "connecting"}
          >
            {activity === "connecting"
              ? "Đang kết nối…"
              : "Bắt đầu phiên kiểm thử"}
          </Button>
        </div>
      ) : (
        <>
          <ol className="chat-messages" aria-label="Lịch sử trò chuyện">
            {messages.length === 0 ? (
              <li className="chat-placeholder">Hãy nhập câu hỏi đầu tiên.</li>
            ) : null}
            {messages.map((message) => (
              <MessageCard key={message.id} message={message} />
            ))}
          </ol>
          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void sendMessage();
            }}
          >
            <label htmlFor="chat-message">Nội dung tin nhắn</label>
            <textarea
              id="chat-message"
              maxLength={12_000}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ví dụ: Hãy giải thích thông tin trong tài liệu và dẫn nguồn theo trang."
              rows={4}
              value={draft}
              disabled={!usable || session.status !== "active"}
            />
            <div className="action-row">
              <Button
                type="submit"
                disabled={
                  !usable ||
                  draft.trim().length === 0 ||
                  activity === "processing"
                }
              >
                Gửi
              </Button>
              {activeTurn ? (
                <Button
                  variant="secondary"
                  onClick={() => void issueCommand("cancel")}
                  disabled={pendingCommand !== null}
                >
                  Dừng trả lời
                </Button>
              ) : null}
              <Button
                variant="secondary"
                onClick={() => void issueCommand("handoff")}
                disabled={!usable || pendingCommand !== null}
              >
                Yêu cầu hỗ trợ
              </Button>
              <Button
                variant="danger"
                onClick={() => void issueCommand("close")}
                disabled={
                  session.status === "closed" || pendingCommand !== null
                }
              >
                {pendingCommand === "close"
                  ? "Đang đóng…"
                  : closeConfirmation
                    ? "Xác nhận đóng phiên"
                    : "Đóng phiên"}
              </Button>
              {closeConfirmation ? (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setCloseConfirmation(false);
                    setNotice("Đã hủy thao tác đóng phiên.");
                  }}
                  disabled={pendingCommand !== null}
                >
                  Giữ phiên
                </Button>
              ) : null}
            </div>
          </form>
        </>
      )}
    </section>
  );
}

function MessageCard({ message }: { readonly message: ConversationMessage }) {
  return (
    <li className={`chat-message chat-message-${message.role}`}>
      <p className="chat-role">
        {message.role === "customer" ? "Bạn" : "Trợ lý"}
      </p>
      <p className="chat-content">{message.content}</p>
      {message.outcome === "refused" ? (
        <p className="chat-outcome">
          Đã từ chối an toàn vì thiếu căn cứ hoặc quyền phù hợp.
        </p>
      ) : null}
      {message.citations.length > 0 ? (
        <details className="chat-citations">
          <summary>Nguồn tham chiếu ({message.citations.length})</summary>
          <ul>
            {message.citations.map((citation) => (
              <li key={`${citation.sourceId}:${citation.revision}`}>
                <span>{citation.title}</span>
                <small>Revision {citation.revision}</small>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </li>
  );
}

function activityLabel(activity: Activity): string {
  return {
    connecting: "Đang kết nối",
    idle: "Chưa kết nối",
    processing: "Đang xử lý",
    ready: "Sẵn sàng",
    unavailable: "Đã khóa",
  }[activity];
}
