import { StatusPanel } from "@/components/feedback/status-panel";
import { ProfilePreferencesForm } from "./profile-preferences-form";
import { updateProfileAction } from "../server/profile-actions";
import styles from "../styles/profile.module.css";
import {
  CustomerAccountApiError,
  getCustomerProfile,
} from "@/platform/api/customer-account/profile-gateway";

export async function ProfilePanel() {
  const state = await getCustomerProfile()
    .then((value) => ({ kind: "ready" as const, value }))
    .catch((error: unknown) => ({
      correlationId:
        error instanceof CustomerAccountApiError
          ? error.correlationId
          : undefined,
      kind: "unavailable" as const,
    }));

  if (state.kind === "ready") {
    return (
      <section className={styles.card} aria-labelledby="profile-form-title">
        <h2 id="profile-form-title">Thông tin cá nhân</h2>
        <ProfilePreferencesForm
          etag={state.value.etag}
          profile={state.value.profile}
          updateAction={updateProfileAction}
        />
      </section>
    );
  }

  return (
    <StatusPanel
      title="Chưa thể tải hồ sơ"
      description={`Dữ liệu được giữ nguyên. Vui lòng thử tải lại sau.${
        state.correlationId ? ` Mã đối chiếu: ${state.correlationId}.` : ""
      }`}
      tone="warning"
    />
  );
}
