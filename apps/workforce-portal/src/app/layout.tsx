import type {Metadata} from 'next';
import type {ReactNode} from 'react';
import '@/styles/globals.css';

export const metadata: Metadata = {
  title: {
    default: 'VFBiz Workforce Portal',
    template: '%s · VFBiz Workforce Portal',
  },
  description: 'Cổng làm việc an toàn dành cho nhân sự VFBiz.',
};

export default function RootLayout({children}: Readonly<{children: ReactNode}>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
