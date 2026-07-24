import { redirect } from "next/navigation";
import { buildGarageVehicleView } from "../model/garage-vehicle-view";
import { GarageVehicleCard } from "./garage-vehicle-card";
import styles from "./garage.module.css";
import { loadApprovedVehicleCatalog } from "@/features/vehicle-catalog/server/approved-catalog";
import { readCustomerGarage } from "@/platform/api/garage-gateway";

export async function GarageListPanel() {
  const [garage, catalog] = await Promise.all([
    readCustomerGarage(),
    loadApprovedVehicleCatalog(),
  ]);

  if (garage.state === "session_required") {
    redirect("/api/auth/login?returnTo=/account/garage");
  }

  if (garage.state !== "ready") {
    return (
      <section className={styles.failureState} role="alert">
        <h2>Chưa thể tải Garage</h2>
        <p>
          {garage.state === "forbidden"
            ? "Phiên hiện tại không có quyền đọc Garage."
            : "Dịch vụ Garage đang tạm thời không khả dụng. Vui lòng thử lại sau."}
        </p>
        {garage.correlationId ? (
          <p className={styles.correlation}>
            Mã đối chiếu: {garage.correlationId}
          </p>
        ) : null}
      </section>
    );
  }

  const vehicles = garage.entries.map((entry) =>
    buildGarageVehicleView(entry, catalog.models),
  );
  if (vehicles.length === 0) {
    return (
      <section className={styles.emptyState}>
        <h2>Garage chưa có xe</h2>
        <p>
          Chọn một mẫu xe và phiên bản từ catalog được phê duyệt để bắt đầu. Bạn
          không cần nhập VIN.
        </p>
      </section>
    );
  }

  return (
    <ul className={styles.vehicleList} aria-label="Danh sách xe">
      {vehicles.map((vehicle) => (
        <li key={vehicle.id}>
          <GarageVehicleCard vehicle={vehicle} />
        </li>
      ))}
    </ul>
  );
}
