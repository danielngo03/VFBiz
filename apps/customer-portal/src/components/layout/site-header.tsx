import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="site-header">
      <nav className="site-nav" aria-label="Điều hướng chính">
        <Link className="wordmark" href="/">
          VFBiz
          <span>Customer Portal</span>
        </Link>
        <Link className="nav-link" href="/account">
          Tài khoản
        </Link>
      </nav>
    </header>
  );
}
