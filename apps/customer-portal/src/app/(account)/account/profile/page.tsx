import { Suspense } from "react";
import { AccountNavigation } from "@/components/layout/account-navigation";
import { PanelSkeleton } from "@/components/feedback/panel-skeleton";
import { ACCOUNT_SECTIONS } from "@/features/account-profile/model/account-navigation";
import { ProfilePanel } from "@/features/account-profile/components/profile-panel";

export const dynamic = "force-dynamic";

export default function ProfilePage() {
  return (
    <div className="account-grid">
      <AccountNavigation items={ACCOUNT_SECTIONS} />
      <main id="main-content" className="content-stack" tabIndex={-1}>
        <header className="page-heading">
          <p className="eyebrow">Tài khoản</p>
          <h1>Hồ sơ của bạn</h1>
          <p>
            Quản lý thông tin hiển thị và preference liên lạc. Credential,
            email xác minh và MFA do hệ thống định danh quản lý riêng.
          </p>
        </header>
        <Suspense
          fallback={<PanelSkeleton fields={4} label="Đang tải hồ sơ" />}
        >
          <ProfilePanel />
        </Suspense>
      </main>
    </div>
  );
}
