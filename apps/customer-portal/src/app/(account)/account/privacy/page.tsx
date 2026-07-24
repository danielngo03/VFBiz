import { Suspense } from "react";
import { AccountNavigation } from "@/components/layout/account-navigation";
import { PanelSkeleton } from "@/components/feedback/panel-skeleton";
import { ACCOUNT_SECTIONS } from "@/features/account-profile/model/account-navigation";
import { ConsentPanel } from "@/features/privacy/components/consent-panel";

export const dynamic = "force-dynamic";

export default function PrivacyPage() {
  return (
    <div className="account-grid">
      <AccountNavigation items={ACCOUNT_SECTIONS} />
      <main id="main-content" className="content-stack" tabIndex={-1}>
        <header className="page-heading">
          <p className="eyebrow">Tài khoản</p>
          <h1>Quyền riêng tư</h1>
          <p>
            Consent được ghi theo purpose, policy version, nguồn và thời điểm.
            Preference liên lạc không tự thay thế consent.
          </p>
        </header>
        <Suspense
          fallback={<PanelSkeleton fields={5} label="Đang tải consent" />}
        >
          <ConsentPanel />
        </Suspense>
      </main>
    </div>
  );
}
