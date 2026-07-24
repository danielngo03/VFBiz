import type {ReactNode} from 'react';
import Link from 'next/link';
import {visibleNavigation} from '@/features/authorization/model/navigation';
import {requireCurrentWorkforceContext} from '@/platform/session/current-workforce-context';

export const dynamic = 'force-dynamic';

export default async function WorkspaceLayout({
  children,
}: Readonly<{children: ReactNode}>) {
  const context = await requireCurrentWorkforceContext();
  const navigation = visibleNavigation(context.entitlements);
  return (
    <div className="workspace">
      <header className="workspace__header">
        <Link className="brand" href="/">VFBiz Workforce</Link>
        <span className="environment-badge">Foundation</span>
      </header>
      <aside className="workspace__sidebar" aria-label="Điều hướng chính">
        <p className="eyebrow">Điều hướng</p>
        <nav aria-label="Chức năng được cấp quyền">
          <ul>
            {navigation.map((item) => (
              <li key={item.href}>
                <Link href={item.href}>{item.label}</Link>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <main className="workspace__main">{children}</main>
    </div>
  );
}
