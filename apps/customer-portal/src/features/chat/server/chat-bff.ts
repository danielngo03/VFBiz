import "server-only";

import {
  customerChatApiRequest,
  customerChatEventStreamRequest,
} from "@/platform/api/customer-api";
import {
  privateJson,
  secureUpstreamResponse,
} from "@/platform/api/http-responses";
import { currentCustomerSession } from "@/platform/session/current-session";
import {
  hasValidCsrfToken,
  hasValidRequestOrigin,
} from "@/platform/session/request-security";

const MAXIMUM_CHAT_BODY_BYTES = 16 * 1024;
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const CONVERSATION_ETAG = /^(?:W\/)?"conversation-(?:0|[1-9][0-9]*)"$/u;
const IDEMPOTENCY_KEY = /^[\x21-\x7e]{16,128}$/u;

export function requireUuidV4(value: string): string {
  if (!UUID_V4.test(value)) throw new Error("Invalid Chat resource identity.");
  return value;
}

export function invalidChatIdentityResponse(): Response {
  return privateJson({ error: "invalid_chat_identity" }, { status: 400 });
}

export async function forwardChatRead(
  path: string,
  headers?: Readonly<Record<string, string>>,
): Promise<Response> {
  try {
    const upstream = await customerChatApiRequest(path, {
      headers,
      method: "GET",
    });
    return secureChatUpstreamResponse(upstream);
  } catch {
    return privateJson({ error: "chat_unavailable" }, { status: 503 });
  }
}

export async function forwardChatMutation(
  request: Request,
  path: string,
): Promise<Response> {
  if (!hasValidRequestOrigin(request)) {
    return privateJson({ error: "invalid_origin" }, { status: 403 });
  }
  const active = await currentCustomerSession();
  if (active === null) {
    return privateJson({ error: "session_required" }, { status: 401 });
  }
  if (!hasValidCsrfToken(request, active.record.session)) {
    return privateJson({ error: "invalid_csrf_token" }, { status: 403 });
  }
  const body = await readBoundedJsonBody(request);
  if (body === null) {
    return privateJson({ error: "invalid_request" }, { status: 400 });
  }
  let headers: Headers;
  try {
    headers = forwardedMutationHeaders(request);
  } catch {
    return privateJson({ error: "invalid_request" }, { status: 400 });
  }
  try {
    const upstream = await customerChatApiRequest(path, {
      body,
      headers,
      method: "POST",
    });
    return secureChatUpstreamResponse(upstream);
  } catch {
    return privateJson({ error: "chat_unavailable" }, { status: 503 });
  }
}

function forwardedMutationHeaders(request: Request): Headers {
  const headers = new Headers({ "content-type": "application/json" });
  const ifMatch = request.headers.get("if-match");
  if (ifMatch !== null) {
    if (!CONVERSATION_ETAG.test(ifMatch)) {
      throw new Error("Invalid conversation revision validator.");
    }
    headers.set("if-match", ifMatch);
  }
  const idempotencyKey = request.headers.get("idempotency-key");
  if (idempotencyKey !== null) {
    if (!IDEMPOTENCY_KEY.test(idempotencyKey)) {
      throw new Error("Invalid idempotency key.");
    }
    headers.set("idempotency-key", idempotencyKey);
  }
  return headers;
}

export async function forwardChatEventStream(
  request: Request,
  path: string,
  lastEventId?: string,
): Promise<Response> {
  try {
    const upstream = await customerChatEventStreamRequest(
      path,
      request.signal,
      lastEventId,
    );
    return secureChatUpstreamResponse(upstream);
  } catch {
    return privateJson({ error: "chat_unavailable" }, { status: 503 });
  }
}

async function readBoundedJsonBody(request: Request): Promise<string | null> {
  const contentType = request.headers.get("content-type")?.split(";", 1)[0];
  if (contentType !== "application/json") return null;
  const declared = request.headers.get("content-length");
  const declaredLength = declared === null ? null : Number(declared);
  if (
    declaredLength !== null &&
    (!Number.isSafeInteger(declaredLength) ||
      declaredLength < 0 ||
      declaredLength > MAXIMUM_CHAT_BODY_BYTES)
  ) {
    return null;
  }
  if (request.body === null) return null;
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > MAXIMUM_CHAT_BODY_BYTES) {
        await reader.cancel("chat request body exceeds limit");
        return null;
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    const body = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    const parsed: unknown = JSON.parse(body);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    return body;
  } catch {
    return null;
  }
}

function secureChatUpstreamResponse(upstream: Response): Response {
  if (upstream.status >= 500) {
    const correlationId = upstream.headers.get("x-correlation-id");
    return privateJson(
      {
        error: "chat_unavailable",
        ...(correlationId === null ? {} : { correlationId }),
      },
      {
        headers:
          correlationId === null ? undefined : { "x-correlation-id": correlationId },
        status: 503,
      },
    );
  }
  return secureUpstreamResponse(upstream);
}
