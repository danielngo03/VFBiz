import type {Metadata} from 'next';
import Link from 'next/link';
import {Button} from '@/components/ui/button';

export const metadata: Metadata = {title: 'Đăng nhập'};

export default async function SignInPage({
  searchParams,
}: Readonly<{
  searchParams: Promise<{returnTo?: string}>;
}>) {
  const requestedReturnTo = (await searchParams).returnTo;
  const returnTo =
    requestedReturnTo?.startsWith('/') &&
    !requestedReturnTo.startsWith('//') &&
    !requestedReturnTo.includes('\\') &&
    !requestedReturnTo.includes('\0')
      ? requestedReturnTo
      : '/authorization';
  const loginHref = `/api/auth/login?${new URLSearchParams({returnTo})}`;
  return (
    <main className="centered-page">
      <section className="panel panel--narrow" aria-labelledby="sign-in-title">
        <p className="eyebrow">Workforce SSO</p>
        <h1 id="sign-in-title">Đăng nhập dành cho nhân sự</h1>
        <p>
          Portal dùng OIDC Authorization Code + PKCE. Token được mã hóa trong
          Redis token vault phía máy chủ; trình duyệt chỉ nhận opaque session.
        </p>
        <Button asChild>
          <Link href={loginHref}>Tiếp tục với Workforce SSO</Link>
        </Button>
      </section>
    </main>
  );
}
