import {
  forwardChatEventStream,
  invalidChatIdentityResponse,
  requireUuidV4,
} from "@/features/chat/server/chat-bff";
import { privateJson } from "@/platform/api/http-responses";

interface RouteContext {
  readonly params: Promise<{ readonly sessionId: string }>;
}

export async function GET(request: Request, context: RouteContext) {
  try {
    const { sessionId } = await context.params;
    const lastEventId = request.headers.get("last-event-id");
    if (
      lastEventId !== null &&
      (lastEventId.length > 256 || !/^[A-Za-z0-9._:-]+$/u.test(lastEventId))
    ) {
      return privateJson({ error: "invalid_event_cursor" }, { status: 400 });
    }
    return forwardChatEventStream(
      request,
      `/api/v1/chat/sessions/${requireUuidV4(sessionId)}/events`,
      lastEventId ?? undefined,
    );
  } catch {
    return invalidChatIdentityResponse();
  }
}
