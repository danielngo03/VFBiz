import { Suspense } from "react";
import { AccountNavigation } from "@/components/layout/account-navigation";
import { ACCOUNT_SECTIONS } from "@/features/account-profile/model/account-navigation";
import { ApprovedCatalogPanel } from "@/features/garage/components/approved-catalog-panel";
import { GarageListPanel } from "@/features/garage/components/garage-list-panel";
import {
  CatalogFormSkeleton,
  GarageListSkeleton,
} from "@/features/garage/components/garage-skeletons";
import styles from "@/features/garage/components/garage.module.css";

export const dynamic = "force-dynamic";

export default function GaragePage() {
  return (
    <div className="account-grid">
      <AccountNavigation items={ACCOUNT_SECTIONS} />
      <main id="main-content" className="content-stack" tabIndex={-1}>
        <header className="page-heading">
          <p className="eyebrow">Garage</p>
          <h1>Xe của bạn</h1>
          <p>
            Lưu mẫu xe và phiên bản để cá nhân hóa trải nghiệm. Xe tự khai báo
            không phải bằng chứng sở hữu đã được xác minh.
          </p>
        </header>
        <div className={styles.layout}>
          <Suspense fallback={<GarageListSkeleton />}>
            <GarageListPanel />
          </Suspense>
          <Suspense fallback={<CatalogFormSkeleton />}>
            <ApprovedCatalogPanel />
          </Suspense>
        </div>
      </main>
    </div>
  );
}
