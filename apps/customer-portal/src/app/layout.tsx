import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";
import { SiteHeader } from "@/components/layout/site-header";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: {
    default: "VFBiz Customer Portal",
    template: "%s · VFBiz Customer Portal",
  },
  description:
    "Cổng tự phục vụ bảo mật cho hồ sơ, quyền riêng tư và Garage của khách hàng.",
};

export default async function RootLayout({
  children,
}: {
  readonly children: ReactNode;
}) {
  // A per-request CSP nonce is injected by proxy.ts. Waiting for the incoming
  // request prevents static HTML from being reused with a different nonce.
  await connection();

  return (
    <html lang="vi">
      <body>
        <a className="skip-link" href="#main-content">
          Bỏ qua tới nội dung chính
        </a>
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
