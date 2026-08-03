import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="site-header">
      <nav className="site-nav" aria-label="Điều hướng chính">
        <Link className="wordmark" href="/">
          VFBiz
          <span>Customer Portal</span>
        </Link>
        <div className="site-nav-links">
          <Link className="nav-link" href="/chat">
            Trợ lý
          </Link>
          <Link className="nav-link" href="/account">
            Tài khoản
          </Link>
        </div>
      </nav>
    </header>
  );
}
