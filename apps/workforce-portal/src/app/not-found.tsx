import Link from 'next/link';

export default function NotFound() {
  return (
    <main className="boundary-state">
      <p className="eyebrow">404</p>
      <h1>Không tìm thấy trang</h1>
      <p>Đường dẫn không tồn tại hoặc capability tương ứng chưa được phát hành.</p>
      <Link href="/">Về trang chính</Link>
    </main>
  );
}
