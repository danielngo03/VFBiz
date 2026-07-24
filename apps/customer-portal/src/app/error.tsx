"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  readonly error: Error & { digest?: string };
  readonly reset: () => void;
}) {
  useEffect(() => {
    // Only an opaque digest is safe to correlate in browser diagnostics.
    if (error.digest) console.error("Customer Portal error", error.digest);
  }, [error.digest]);

  return (
    <main id="main-content" className="page-frame">
      <section className="status-card" role="alert" aria-labelledby="error-title">
        <p className="eyebrow">Không thể tải nội dung</p>
        <h1 id="error-title">Đã xảy ra lỗi tạm thời</h1>
        <p>Dữ liệu chưa được thay đổi. Vui lòng thử lại yêu cầu.</p>
        <Button type="button" onClick={reset}>
          Thử lại
        </Button>
      </section>
    </main>
  );
}
