import { forwardChatMutation } from "@/features/chat/server/chat-bff";

export function POST(request: Request) {
  return forwardChatMutation(request, "/api/v1/chat/sessions");
}
