import { StatusPanel } from "@/components/feedback/status-panel";
import {
  CustomerAccountApiError,
  listCustomerSessions,
} from "@/platform/api/customer-account/security-gateway";
import {
  logoutAllSessionsAction,
  revokeSessionAction,
} from "../server/security-actions";
import { SessionList } from "./session-list";

export async function SessionsPanel() {
  const state = await listCustomerSessions()
    .then((sessions) => ({ kind: "ready" as const, sessions }))
    .catch((error: unknown) => ({
      correlationId:
        error instanceof CustomerAccountApiError
          ? error.correlationId
          : null,
      kind: "unavailable" as const,
    }));
  if (state.kind === "ready") {
    return (
      <SessionList
        logoutAllAction={logoutAllSessionsAction}
        revokeAction={revokeSessionAction}
        sessions={state.sessions}
      />
    );
  }
  return (
    <StatusPanel
      title="Chưa thể tải danh sách phiên"
      description={`Không có thao tác thu hồi nào được thực hiện. Vui lòng thử lại sau.${
        state.correlationId ? ` Mã đối chiếu: ${state.correlationId}.` : ""
      }`}
      tone="warning"
    />
  );
}
