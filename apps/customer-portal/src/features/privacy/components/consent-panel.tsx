import { randomUUID } from "node:crypto";
import { StatusPanel } from "@/components/feedback/status-panel";
import {
  CustomerAccountApiError,
  listCustomerConsents,
} from "@/platform/api/customer-account/privacy-gateway";
import { updateConsentsAction } from "../server/privacy-actions";
import { ConsentForm } from "./consent-form";
import styles from "../styles/privacy.module.css";

export async function ConsentPanel() {
  const state = await listCustomerConsents()
    .then((consents) => ({ consents, kind: "ready" as const }))
    .catch((error: unknown) => ({
      correlationId:
        error instanceof CustomerAccountApiError
          ? error.correlationId
          : null,
      kind: "unavailable" as const,
    }));

  if (state.kind === "ready") {
    return (
      <section className={styles.card} aria-labelledby="consent-title">
        <h2 id="consent-title">Lựa chọn consent</h2>
        <ConsentForm
          consents={state.consents}
          idempotencyKey={randomUUID()}
          updateAction={updateConsentsAction}
        />
      </section>
    );
  }

  return (
    <StatusPanel
      title="Chưa thể tải consent"
      description={`Dữ liệu được giữ nguyên và không có consent nào bị tự thay đổi.${
        state.correlationId ? ` Mã đối chiếu: ${state.correlationId}.` : ""
      }`}
      tone="warning"
    />
  );
}
