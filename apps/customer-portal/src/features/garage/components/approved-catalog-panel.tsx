import { randomUUID } from "node:crypto";
import { loadApprovedVehicleCatalog } from "@/features/vehicle-catalog/server/approved-catalog";
import { AddVehicleForm } from "./add-vehicle-form";
import styles from "./garage.module.css";

export async function ApprovedCatalogPanel() {
  const catalog = await loadApprovedVehicleCatalog();
  const models = catalog.models.filter(
    (model) =>
      model.commercialStatus === "active" &&
      model.variants.some((variant) => variant.commercialStatus === "active"),
  );

  return (
    <section className={styles.panel} aria-labelledby="add-vehicle">
      <h2 id="add-vehicle">Thêm xe</h2>
      {catalog.state === "unavailable" ? (
        <div role="alert">
          <p>
            Catalog xe đang tạm thời không khả dụng. Garage hiện tại vẫn được
            giữ nguyên.
          </p>
        </div>
      ) : catalog.state === "stale" ? (
        <div role="status">
          <p>
            Catalog đang được đồng bộ. Tạm thời chưa thể thêm xe để tránh chọn
            dữ liệu cũ.
          </p>
        </div>
      ) : models.length === 0 ? (
        <div role="status">
          <p>Chưa có mẫu xe active trong catalog được phê duyệt.</p>
        </div>
      ) : (
        <AddVehicleForm initialRequestId={randomUUID()} models={models} />
      )}
    </section>
  );
}
