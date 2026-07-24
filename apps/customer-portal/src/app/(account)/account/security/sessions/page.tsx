import { Suspense } from "react";
import Link from "next/link";
import { AccountNavigation } from "@/components/layout/account-navigation";
import { PanelSkeleton } from "@/components/feedback/panel-skeleton";
import { Button } from "@/components/ui/button";
import { ACCOUNT_SECTIONS } from "@/features/account-profile/model/account-navigation";
import { SessionsPanel } from "@/features/account-security/components/sessions-panel";

export const dynamic = "force-dynamic";

export default function AccountSessionsPage() {
  return (
    <div className="account-grid">
      <AccountNavigation items={ACCOUNT_SECTIONS} />
      <main id="main-content" className="content-stack" tabIndex={-1}>
        <header className="page-heading">
          <p className="eyebrow">Bảo mật</p>
          <h1>Các phiên đăng nhập</h1>
          <p>
            Xem metadata tối thiểu để nhận biết hoạt động và thu hồi phiên không
            còn sử dụng. Metadata này không phải device identity.
          </p>
          <Button asChild variant="ghost">
            <Link href="/account/security">Quay lại bảo mật</Link>
          </Button>
        </header>
        <Suspense
          fallback={<PanelSkeleton fields={4} label="Đang tải phiên đăng nhập" />}
        >
          <SessionsPanel />
        </Suspense>
      </main>
    </div>
  );
}
