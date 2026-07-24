import Link from 'next/link';
import {Button} from '@/components/ui/button';

export default function HomePage() {
  return (
    <main className="welcome">
      <section className="welcome__content" aria-labelledby="welcome-title">
        <p className="eyebrow">VFBiz · Workforce</p>
        <h1 id="welcome-title">Không gian làm việc của đội ngũ VFBiz</h1>
        <p className="welcome__lead">
          Một cổng thống nhất cho vận hành, kiểm soát phát hành và quản trị
          quyền. Mọi hành động nhạy cảm đều được API xác minh và ghi audit.
        </p>
        <Button asChild>
          <Link href="/sign-in">Đăng nhập bằng tài khoản nhân sự</Link>
        </Button>
      </section>
      <aside className="trust-card" aria-label="Nguyên tắc bảo mật">
        <h2>Quyền hạn được kiểm soát tại máy chủ</h2>
        <ul>
          <li>SSO và MFA cho workforce identity</li>
          <li>Capability theo phạm vi tổ chức</li>
          <li>Maker-checker cho thao tác đặc quyền</li>
          <li>Không lưu token trong trình duyệt</li>
        </ul>
      </aside>
    </main>
  );
}
