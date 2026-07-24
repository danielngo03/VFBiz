'use client';

import {useEffect} from 'react';
import {Button} from '@/components/ui/button';

export default function UnexpectedError({
  error,
  reset,
}: {
  readonly error: Error & {digest?: string};
  readonly reset: () => void;
}) {
  useEffect(() => {
    console.error('Workforce Portal render failed', {digest: error.digest});
  }, [error]);
  return (
    <main className="boundary-state">
      <p className="eyebrow">Lỗi ngoài dự kiến</p>
      <h1>Không thể hiển thị trang này</h1>
      <p>Vui lòng thử lại. Raw upstream error không được hiển thị tại đây.</p>
      <Button onClick={reset}>Thử lại</Button>
    </main>
  );
}
