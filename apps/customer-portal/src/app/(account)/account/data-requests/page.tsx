import { Suspense } from "react";
import { AccountNavigation } from "@/components/layout/account-navigation";
import { PanelSkeleton } from "@/components/feedback/panel-skeleton";
import { ACCOUNT_SECTIONS } from "@/features/account-profile/model/account-navigation";
import { DataRequestsContent } from "@/features/privacy/components/data-requests-content";

export const dynamic = "force-dynamic";

export default function DataRequestsPage() {
  return (
    <div className="account-grid">
      <AccountNavigation items={ACCOUNT_SECTIONS} />
      <main id="main-content" className="content-stack" tabIndex={-1}>
        <header className="page-heading">
          <p className="eyebrow">Quyền riêng tư</p>
          <h1>Yêu cầu dữ liệu</h1>
          <p>
            Tạo và theo dõi yêu cầu xuất hoặc xóa dữ liệu. Việc xử lý diễn ra
            bất đồng bộ và có thể chịu giới hạn lưu giữ hợp pháp.
          </p>
        </header>
        <Suspense
          fallback={
            <PanelSkeleton fields={3} label="Đang tải yêu cầu dữ liệu" />
          }
        >
          <DataRequestsContent />
        </Suspense>
      </main>
    </div>
  );
}
