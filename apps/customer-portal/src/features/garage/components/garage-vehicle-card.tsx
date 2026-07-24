"use client";

import { useActionState } from "react";
import { Button } from "@/components/ui/button";
import { ConfirmationDialog } from "@/components/ui/confirmation-dialog";
import type { GarageVehicleView } from "@/features/garage/model/garage-vehicle-view";
import { INITIAL_GARAGE_ACTION_STATE } from "@/features/garage/model/garage-action-state";
import {
  vehicleVerificationDescription,
  vehicleVerificationLabel,
} from "@/features/garage/model/garage-vehicle-view";
import {
  removeGarageVehicleAction,
  renameGarageVehicleAction,
  setPrimaryGarageVehicleAction,
} from "@/features/garage/server/garage-actions";
import { GarageActionMessage } from "./action-message";
import styles from "./garage.module.css";

export function GarageVehicleCard({
  vehicle,
}: {
  readonly vehicle: GarageVehicleView;
}) {
  const [renameState, renameAction, renamePending] = useActionState(
    renameGarageVehicleAction,
    INITIAL_GARAGE_ACTION_STATE,
  );
  const [primaryState, primaryAction, primaryPending] = useActionState(
    setPrimaryGarageVehicleAction,
    INITIAL_GARAGE_ACTION_STATE,
  );
  const [removeState, removeAction, removePending] = useActionState(
    removeGarageVehicleAction,
    INITIAL_GARAGE_ACTION_STATE,
  );

  return (
    <article className={styles.vehicleCard}>
      <header className={styles.vehicleHeader}>
        <div>
          <p className={styles.vehicleMeta}>
            {vehicle.modelName && vehicle.variantName
              ? `${vehicle.modelName} · ${vehicle.variantName}`
              : "Catalog hiện không có thông tin hiển thị cho xe này"}
          </p>
          <h2>{vehicle.displayName}</h2>
        </div>
        {vehicle.isPrimary ? (
          <span className={styles.primaryBadge}>Xe chính</span>
        ) : null}
      </header>

      <section
        className={styles.verification}
        aria-label={`Trạng thái: ${vehicleVerificationLabel(vehicle.verificationState)}`}
      >
        <strong>{vehicleVerificationLabel(vehicle.verificationState)}</strong>
        <p>{vehicleVerificationDescription(vehicle.verificationState)}</p>
      </section>

      <form action={renameAction} className={styles.inlineForm}>
        <input name="entryId" type="hidden" value={vehicle.id} />
        <input name="version" type="hidden" value={vehicle.version} />
        <div className={styles.field}>
          <label htmlFor={`nickname-${vehicle.id}`}>Tên gợi nhớ</label>
          <input
            defaultValue={vehicle.nickname ?? ""}
            id={`nickname-${vehicle.id}`}
            maxLength={80}
            name="nickname"
            type="text"
          />
        </div>
        <Button disabled={renamePending} type="submit" variant="secondary">
          {renamePending ? "Đang lưu…" : "Đổi tên"}
        </Button>
        <GarageActionMessage state={renameState} />
      </form>

      <div className={styles.cardActions}>
        {!vehicle.isPrimary ? (
          <form action={primaryAction}>
            <input name="entryId" type="hidden" value={vehicle.id} />
            <input name="version" type="hidden" value={vehicle.version} />
            <Button disabled={primaryPending} type="submit" variant="secondary">
              {primaryPending ? "Đang cập nhật…" : "Đặt làm xe chính"}
            </Button>
            <GarageActionMessage state={primaryState} />
          </form>
        ) : null}
        <ConfirmationDialog
          actionLabel="Xóa khỏi Garage"
          description="Thông tin xe sẽ không còn xuất hiện trong Garage. Hành động này không xóa dữ liệu kiểm toán."
          onConfirm={() => {
            const form = document.getElementById(
              `remove-${vehicle.id}`,
            ) as HTMLFormElement | null;
            form?.requestSubmit();
          }}
          title={`Xóa ${vehicle.displayName}?`}
        >
          <Button disabled={removePending} variant="danger">
            Xóa xe
          </Button>
        </ConfirmationDialog>
        <form
          action={removeAction}
          className={styles.hiddenForm}
          id={`remove-${vehicle.id}`}
        >
          <input name="entryId" type="hidden" value={vehicle.id} />
          <input name="version" type="hidden" value={vehicle.version} />
        </form>
      </div>
      <GarageActionMessage state={removeState} />
    </article>
  );
}
