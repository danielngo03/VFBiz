"use client";

import type { components } from "@vfbiz/api-client";
import { useActionState, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { INITIAL_GARAGE_ACTION_STATE } from "@/features/garage/model/garage-action-state";
import { addGarageVehicleAction } from "@/features/garage/server/garage-actions";
import { GarageActionMessage } from "./action-message";
import styles from "./garage.module.css";

type VehicleModel = components["schemas"]["VehicleModelProjection"];

export function AddVehicleForm({
  initialRequestId,
  models,
}: {
  readonly initialRequestId: string;
  readonly models: readonly VehicleModel[];
}) {
  const [modelId, setModelId] = useState(models[0]?.id ?? "");
  const [state, action, pending] = useActionState(
    addGarageVehicleAction,
    INITIAL_GARAGE_ACTION_STATE,
  );
  const selectedModel = useMemo(
    () => models.find((model) => model.id === modelId) ?? models[0],
    [modelId, models],
  );
  const variants =
    selectedModel?.variants.filter(
      (variant) => variant.commercialStatus === "active",
    ) ?? [];

  return (
    <form action={action} className={styles.form} noValidate>
      <input name="requestId" type="hidden" value={initialRequestId} />
      <div className={styles.field}>
        <label htmlFor="garage-model">Mẫu xe</label>
        <select
          id="garage-model"
          name="modelId"
          value={selectedModel?.id ?? ""}
          onChange={(event) => setModelId(event.target.value)}
          required
        >
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.name}
            </option>
          ))}
        </select>
      </div>
      <div className={styles.field}>
        <label htmlFor="garage-variant">Phiên bản</label>
        <select id="garage-variant" name="variantId" required>
          {variants.map((variant) => (
            <option key={variant.id} value={variant.id}>
              {variant.name}
            </option>
          ))}
        </select>
        {variants.length === 0 ? (
          <p className={styles.help}>
            Mẫu xe này chưa có phiên bản active trong catalog được phê duyệt.
          </p>
        ) : null}
      </div>
      <div className={styles.field}>
        <label htmlFor="garage-nickname">Tên gợi nhớ (không bắt buộc)</label>
        <input
          id="garage-nickname"
          maxLength={80}
          name="nickname"
          placeholder="Ví dụ: Xe gia đình"
          type="text"
        />
      </div>
      <label className={styles.checkbox}>
        <input name="isPrimary" type="checkbox" />
        Đặt làm xe chính
      </label>
      <p className={styles.help}>
        Garage hiện không yêu cầu VIN. Xe được thêm sẽ bắt đầu ở trạng thái Chưa
        xác minh.
      </p>
      <GarageActionMessage state={state} />
      <Button disabled={pending || variants.length === 0} type="submit">
        {pending ? "Đang thêm…" : "Thêm vào Garage"}
      </Button>
    </form>
  );
}
