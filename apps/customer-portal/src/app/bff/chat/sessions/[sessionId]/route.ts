import {
  forwardChatRead,
  invalidChatIdentityResponse,
  requireUuidV4,
} from "@/features/chat/server/chat-bff";

interface RouteContext {
  readonly params: Promise<{ readonly sessionId: string }>;
}

export async function GET(_: Request, context: RouteContext) {
  try {
    const { sessionId } = await context.params;
    return forwardChatRead(`/api/v1/chat/sessions/${requireUuidV4(sessionId)}`);
  } catch {
    return invalidChatIdentityResponse();
  }
}
