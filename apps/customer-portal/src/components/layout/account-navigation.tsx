import Link from "next/link";
import type { AccountSection } from "@/features/account-profile/model/account-navigation";

export function AccountNavigation({
  items,
}: {
  readonly items: readonly AccountSection[];
}) {
  return (
    <aside className="account-sidebar">
      <nav aria-label="Quản lý tài khoản">
        <p className="sidebar-label">Khu vực tài khoản</p>
        <ul className="sidebar-list">
          {items.map((item) => (
            <li key={item.id}>
              <Link href={item.href}>{item.label}</Link>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
