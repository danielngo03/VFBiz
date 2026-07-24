import Link from "next/link";
import { redirect } from "next/navigation";
import { AccountNavigation } from "@/components/layout/account-navigation";
import { StatusPanel } from "@/components/feedback/status-panel";
import { Button } from "@/components/ui/button";
import { ACCOUNT_SECTIONS } from "@/features/account-profile/model/account-navigation";
import { SessionSecuritySummary } from "@/features/account-security/components/session-security-summary";
import { currentCustomerSession } from "@/platform/session/current-session";

export const dynamic = "force-dynamic";

export default async function AccountPage() {
  const active = await currentCustomerSession();
  if (active === null) {
    redirect("/api/auth/login?returnTo=/account");
  }
  return (
    <div className="account-grid">
      <AccountNavigation items={ACCOUNT_SECTIONS} />
      <main id="main-content" className="content-stack" tabIndex={-1}>
        <header className="page-heading">
          <p className="eyebrow">Tài khoản</p>
          <h1>Tổng quan tài khoản</h1>
          <p>
            Kiểm tra phiên hiện tại trước khi quản lý thông tin hoặc thực hiện
            thao tác nhạy cảm.
          </p>
        </header>
        <SessionSecuritySummary session={active.record.session} />
        <StatusPanel
          title="Các hành trình tài khoản đang được hoàn thiện"
          description="Profile, consent, yêu cầu dữ liệu và Garage sẽ được mở theo từng capability đã được kiểm thử."
          tone="information"
        />
        <div className="action-row">
          <Button asChild>
            <Link href="/api/auth/configure-mfa?returnTo=/account">
              Cấu hình MFA
            </Link>
          </Button>
        </div>
      </main>
    </div>
  );
}
