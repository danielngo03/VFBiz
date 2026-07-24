import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main id="main-content" className="page-frame">
      <section className="status-card" aria-labelledby="not-found-title">
        <p className="eyebrow">404</p>
        <h1 id="not-found-title">Không tìm thấy trang</h1>
        <p>Đường dẫn có thể đã thay đổi hoặc bạn chưa có quyền truy cập.</p>
        <Button asChild>
          <Link href="/">Về trang chủ</Link>
        </Button>
      </section>
    </main>
  );
}
