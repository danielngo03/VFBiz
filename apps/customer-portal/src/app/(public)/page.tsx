import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function HomePage() {
  return (
    <main id="main-content" className="page-frame" tabIndex={-1}>
      <section className="hero-panel" aria-labelledby="portal-title">
        <p className="eyebrow">Customer Portal</p>
        <h1 id="portal-title">Quản lý trải nghiệm sở hữu xe tại một nơi</h1>
        <p className="lede">
          Truy cập hồ sơ, bảo mật tài khoản, quyền riêng tư và Garage bằng một
          phiên đăng nhập được bảo vệ.
        </p>
        <div className="action-row">
          <Button asChild>
            <Link href="/api/auth/login?returnTo=/account">Đăng nhập</Link>
          </Button>
          <Button asChild variant="secondary">
            <Link href="/api/auth/register?returnTo=/account">
              Tạo tài khoản
            </Link>
          </Button>
        </div>
      </section>
    </main>
  );
}
