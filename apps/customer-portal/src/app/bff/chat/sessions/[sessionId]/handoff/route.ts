import {
  forwardChatMutation,
  invalidChatIdentityResponse,
  requireUuidV4,
} from "@/features/chat/server/chat-bff";

interface RouteContext {
  readonly params: Promise<{ readonly sessionId: string }>;
}

export async function POST(request: Request, context: RouteContext) {
  try {
    const { sessionId } = await context.params;
    return forwardChatMutation(
      request,
      `/api/v1/chat/sessions/${requireUuidV4(sessionId)}/handoff`,
    );
  } catch {
    return invalidChatIdentityResponse();
  }
}
