import { StatusPanel } from "@/components/feedback/status-panel";
import {
  CustomerAccountApiError,
  getIdentitySecurity,
} from "@/platform/api/customer-account/security-gateway";
import { SessionSecuritySummary } from "./session-security-summary";

export async function SecurityPanel() {
  const state = await getIdentitySecurity()
    .then((security) => ({ kind: "ready" as const, security }))
    .catch((error: unknown) => ({
      kind: "unavailable" as const,
      reference:
        error instanceof CustomerAccountApiError
          ? error.correlationId
          : undefined,
    }));
  if (state.kind === "ready") {
    return <SessionSecuritySummary security={state.security} />;
  }
  return (
    <StatusPanel
      title="Chưa thể xác minh trạng thái bảo mật"
      description={`Hệ thống không suy đoán trạng thái email hoặc MFA khi CIAM/API chưa phản hồi.${
        state.reference ? ` Mã đối chiếu: ${state.reference}.` : ""
      }`}
      tone="warning"
    />
  );
}
