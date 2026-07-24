import { Skeleton } from "@/components/ui/skeleton";
import styles from "./garage.module.css";

export function GarageListSkeleton() {
  return (
    <section
      className={styles.skeletonStack}
      aria-busy="true"
      aria-label="Đang tải danh sách xe"
      role="status"
    >
      <span className="sr-only">Đang tải danh sách xe</span>
      {[0, 1].map((item) => (
        <div className={styles.vehicleCard} key={item}>
          <Skeleton height="1.5rem" width="46%" />
          <Skeleton height="0.85rem" width="68%" />
          <Skeleton height="4.5rem" width="100%" />
        </div>
      ))}
    </section>
  );
}

export function CatalogFormSkeleton() {
  return (
    <section
      className={styles.panel}
      aria-busy="true"
      aria-label="Đang tải catalog xe"
      role="status"
    >
      <span className="sr-only">Đang tải catalog xe</span>
      <Skeleton height="1.5rem" width="42%" />
      <div className={styles.skeletonFields}>
        <Skeleton height="2.75rem" width="100%" />
        <Skeleton height="2.75rem" width="100%" />
        <Skeleton height="2.75rem" width="100%" />
      </div>
    </section>
  );
}
