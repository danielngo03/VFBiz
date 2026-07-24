"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useActionState } from "react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import {
  initialProfileActionState,
  type ProfileActionState,
} from "@/features/account-profile/model/profile-action-state";
import type { CustomerProfile } from "@/platform/api/customer-account/profile-contracts";
import {
  profilePreferencesSchema,
  type ProfilePreferencesInput,
} from "@/features/account-profile/schemas/profile-preferences";
import styles from "../styles/profile.module.css";

export type ProfilePreferencesFormProps =
  | {
      readonly etag: string;
      readonly initialValue?: never;
      readonly onSubmit?: never;
      readonly profile: CustomerProfile;
      readonly updateAction: (
        previous: ProfileActionState,
        formData: FormData,
      ) => Promise<ProfileActionState>;
    }
  | {
      readonly etag?: never;
      readonly initialValue: ProfilePreferencesInput;
      readonly onSubmit: (value: ProfilePreferencesInput) => Promise<void>;
      readonly profile?: never;
      readonly updateAction?: never;
    };

function fieldMessage(
  messages: readonly string[] | undefined,
  id: string,
) {
  return messages?.[0] ? (
    <p id={id} className={styles.fieldError} role="alert">
      {messages[0]}
    </p>
  ) : null;
}

function EnterpriseProfilePreferencesForm({
  etag,
  profile,
  updateAction,
}: {
  readonly etag: string;
  readonly profile: CustomerProfile;
  readonly updateAction: (
    previous: ProfileActionState,
    formData: FormData,
  ) => Promise<ProfileActionState>;
}) {
  const [state, formAction, pending] = useActionState(
    updateAction,
    initialProfileActionState,
  );

  return (
    <form
      action={formAction}
      className={styles.form}
      noValidate
      aria-label="Hồ sơ và tùy chọn liên lạc"
    >
      <input name="expectedEtag" type="hidden" value={etag} />
      <div className={styles.field}>
        <label htmlFor="display-name">Tên hiển thị</label>
        <input
          id="display-name"
          aria-describedby={
            state.fieldErrors?.displayName
              ? "display-name-error"
              : "display-name-help"
          }
          aria-invalid={state.fieldErrors?.displayName ? "true" : "false"}
          autoComplete="name"
          defaultValue={profile.displayName ?? ""}
          maxLength={120}
          name="displayName"
        />
        <p id="display-name-help" className={styles.help}>
          Bạn có thể để trống. Email và credential được CIAM quản lý, không sửa
          tại biểu mẫu này.
        </p>
        {fieldMessage(state.fieldErrors?.displayName, "display-name-error")}
      </div>

      <div className={styles.twoColumns}>
        <div className={styles.field}>
          <label htmlFor="locale">Ngôn ngữ</label>
          <select id="locale" defaultValue={profile.locale} name="locale">
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
          </select>
          {fieldMessage(state.fieldErrors?.locale, "locale-error")}
        </div>
        <div className={styles.field}>
          <label htmlFor="timezone">Múi giờ</label>
          <select
            id="timezone"
            defaultValue={profile.timezone}
            name="timezone"
          >
            <option value="Asia/Ho_Chi_Minh">Việt Nam (UTC+7)</option>
            <option value="Asia/Bangkok">Bangkok (UTC+7)</option>
            <option value="Asia/Singapore">Singapore (UTC+8)</option>
            <option value="UTC">UTC</option>
          </select>
          {fieldMessage(state.fieldErrors?.timezone, "timezone-error")}
        </div>
      </div>

      <div className={styles.field}>
        <label htmlFor="market">Thị trường</label>
        <input
          id="market"
          aria-describedby="market-help"
          disabled
          value="Việt Nam"
        />
        <p id="market-help" className={styles.help}>
          Thị trường do hồ sơ doanh nghiệp xác định và hiện chưa thể tự thay
          đổi.
        </p>
      </div>

      <fieldset className={styles.fieldset}>
        <legend>Kênh liên lạc ưu tiên</legend>
        <p className={styles.help}>
          Đây là preference liên lạc. Consent cho từng purpose được quản lý
          riêng tại mục Quyền riêng tư.
        </p>
        {(
          [
            ["email", "Email", profile.communicationPreferences.email],
            ["sms", "SMS", profile.communicationPreferences.sms],
            ["push", "Thông báo đẩy", profile.communicationPreferences.push],
          ] as const
        ).map(([name, label, checked]) => (
          <label className={styles.checkbox} key={name}>
            <input defaultChecked={checked} name={name} type="checkbox" />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>

      <div aria-live="polite" className={styles.result}>
        {state.message ? (
          <p
            className={
              state.status === "success"
                ? styles.successMessage
                : styles.errorMessage
            }
            role={state.status === "success" ? "status" : "alert"}
          >
            {state.message}
            {state.correlationId
              ? ` Mã đối chiếu: ${state.correlationId}.`
              : ""}
          </p>
        ) : null}
        {state.status === "conflict" ? (
          <a className={styles.reloadLink} href="/account/profile">
            Tải lại dữ liệu mới nhất
          </a>
        ) : null}
      </div>

      <Button disabled={pending} type="submit">
        {pending ? "Đang lưu…" : "Lưu thay đổi"}
      </Button>
    </form>
  );
}

function LegacyProfilePreferencesForm({
  initialValue,
  onSubmit,
}: {
  readonly initialValue: ProfilePreferencesInput;
  readonly onSubmit: (value: ProfilePreferencesInput) => Promise<void>;
}) {
  const {
    formState: { errors, isSubmitting },
    handleSubmit,
    register,
  } = useForm<ProfilePreferencesInput>({
    defaultValues: initialValue,
    resolver: zodResolver(profilePreferencesSchema),
  });
  return (
    <form
      aria-label="Thông tin hiển thị"
      className={styles.form}
      noValidate
      onSubmit={handleSubmit(onSubmit)}
    >
      <div className={styles.field}>
        <label htmlFor="legacy-display-name">Tên hiển thị</label>
        <input
          id="legacy-display-name"
          aria-invalid={errors.displayName ? "true" : "false"}
          {...register("displayName")}
        />
        {errors.displayName ? (
          <p className={styles.fieldError} role="alert">
            {errors.displayName.message}
          </p>
        ) : null}
      </div>
      <div className={styles.field}>
        <label htmlFor="legacy-locale">Ngôn ngữ</label>
        <select id="legacy-locale" {...register("locale")}>
          <option value="vi-VN">Tiếng Việt</option>
          <option value="en-US">English</option>
        </select>
      </div>
      <div className={styles.field}>
        <label htmlFor="legacy-timezone">Múi giờ</label>
        <input id="legacy-timezone" {...register("timezone")} />
      </div>
      <Button disabled={isSubmitting} type="submit">
        {isSubmitting ? "Đang lưu…" : "Lưu thay đổi"}
      </Button>
    </form>
  );
}

export function ProfilePreferencesForm(
  props: ProfilePreferencesFormProps,
) {
  if (props.profile !== undefined && props.etag !== undefined) {
    return (
      <EnterpriseProfilePreferencesForm
        etag={props.etag}
        profile={props.profile}
        updateAction={props.updateAction}
      />
    );
  }
  return (
    <LegacyProfilePreferencesForm
      initialValue={props.initialValue}
      onSubmit={props.onSubmit}
    />
  );
}
