import { Suspense } from "react";
import { AccountNavigation } from "@/components/layout/account-navigation";
import { PanelSkeleton } from "@/components/feedback/panel-skeleton";
import { ACCOUNT_SECTIONS } from "@/features/account-profile/model/account-navigation";
import { SecurityPanel } from "@/features/account-security/components/security-panel";

export const dynamic = "force-dynamic";

export default function AccountSecurityPage() {
  return (
    <div className="account-grid">
      <AccountNavigation items={ACCOUNT_SECTIONS} />
      <main id="main-content" className="content-stack" tabIndex={-1}>
        <header className="page-heading">
          <p className="eyebrow">Tài khoản</p>
          <h1>Bảo mật đăng nhập</h1>
          <p>
            CIAM quản lý credential và MFA. Portal chỉ hiển thị evidence đã xác
            minh và không coi IP hay tên thiết bị là yếu tố định danh.
          </p>
        </header>
        <Suspense
          fallback={
            <PanelSkeleton fields={3} label="Đang kiểm tra bảo mật" />
          }
        >
          <SecurityPanel />
        </Suspense>
      </main>
    </div>
  );
}
