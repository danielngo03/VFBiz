import type { GarageActionState } from "@/features/garage/model/garage-action-state";
import styles from "./garage.module.css";

export function GarageActionMessage({
  state,
}: {
  readonly state: GarageActionState;
}) {
  if (!state.message) return null;
  return (
    <p
      className={
        state.code === "completed" ? styles.successMessage : styles.errorMessage
      }
      role={state.code === "completed" ? "status" : "alert"}
      aria-live="polite"
    >
      {state.message}
      {state.correlationId ? (
        <span className={styles.correlation}>
          {" "}
          Mã đối chiếu: {state.correlationId}
        </span>
      ) : null}
    </p>
  );
}
