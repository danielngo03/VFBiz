"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import {
  initialConsentActionState,
  type PrivacyActionState,
} from "@/features/privacy/model/privacy-action-state";
import type { ConsentRecord } from "@/platform/api/customer-account/privacy-contracts";
import styles from "../styles/privacy.module.css";

const PURPOSE_COPY: Record<
  ConsentRecord["purpose"],
  { readonly description: string; readonly label: string }
> = {
  analytics: {
    description: "Đo lường cách portal được sử dụng để cải thiện trải nghiệm.",
    label: "Phân tích trải nghiệm",
  },
  marketing_email: {
    description: "Nhận nội dung tiếp thị qua email.",
    label: "Tiếp thị qua email",
  },
  marketing_push: {
    description: "Nhận nội dung tiếp thị qua thông báo đẩy.",
    label: "Tiếp thị qua thông báo đẩy",
  },
  marketing_sms: {
    description: "Nhận nội dung tiếp thị qua SMS.",
    label: "Tiếp thị qua SMS",
  },
  personalization: {
    description: "Cá nhân hóa nội dung dựa trên dữ liệu được phép sử dụng.",
    label: "Cá nhân hóa",
  },
};

export function ConsentForm({
  consents,
  idempotencyKey,
  updateAction,
}: {
  readonly consents: readonly ConsentRecord[];
  readonly idempotencyKey: string;
  readonly updateAction: (
    previous: PrivacyActionState,
    formData: FormData,
  ) => Promise<PrivacyActionState>;
}) {
  const [state, formAction, pending] = useActionState(
    updateAction,
    initialConsentActionState,
  );

  if (consents.length === 0) {
    return (
      <p className={styles.empty} role="status">
        API chưa công bố purpose consent đang hoạt động cho tài khoản này. Không
        có lựa chọn nào được tự suy đoán hoặc tự tạo.
      </p>
    );
  }

  return (
    <form action={formAction} className={styles.form}>
      <input name="idempotencyKey" type="hidden" value={idempotencyKey} />
      <fieldset className={styles.fieldset}>
        <legend>Consent đang có hiệu lực</legend>
        {consents.map((consent) => {
          const copy = PURPOSE_COPY[consent.purpose];
          return (
            <label className={styles.consent} key={consent.purpose}>
              <input
                defaultChecked={consent.state === "granted"}
                name={`consent:${consent.purpose}`}
                type="checkbox"
              />
              <span>
                <strong>{copy.label}</strong>
                <small>{copy.description}</small>
                <small>
                  Policy {consent.policyVersion} · Nguồn {consent.source} · Cập
                  nhật{" "}
                  {new Intl.DateTimeFormat("vi-VN", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(consent.occurredAt))}
                </small>
              </span>
            </label>
          );
        })}
      </fieldset>
      <div aria-live="polite">
        {state.message ? (
          <p
            className={state.ok ? styles.success : styles.error}
            role={state.ok ? "status" : "alert"}
          >
            {state.message}
            {state.correlationId
              ? ` Mã đối chiếu: ${state.correlationId}.`
              : ""}
          </p>
        ) : null}
      </div>
      <Button disabled={pending} type="submit">
        {pending ? "Đang lưu…" : "Lưu lựa chọn"}
      </Button>
    </form>
  );
}
