import { redirect } from "next/navigation";
import { ChatWorkspace } from "@/features/chat/components/chat-workspace";
import { currentCustomerSession } from "@/platform/session/current-session";

export const dynamic = "force-dynamic";

export default async function ChatPage() {
  if ((await currentCustomerSession()) === null) {
    redirect("/api/auth/login?returnTo=/chat");
  }
  return (
    <main id="main-content" className="chat-page" tabIndex={-1}>
      <ChatWorkspace />
    </main>
  );
}
