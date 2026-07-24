import type {ReactNode} from 'react';

interface ResourcePageProps {
  readonly eyebrow: string;
  readonly title: string;
  readonly description: string;
  readonly children: ReactNode;
}

export function ResourcePage({
  eyebrow,
  title,
  description,
  children,
}: ResourcePageProps) {
  return (
    <section className="resource-page" aria-labelledby="resource-page-title">
      <header className="resource-page__header">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1 id="resource-page-title">{title}</h1>
          <p>{description}</p>
        </div>
        <span className="read-only-badge">Chỉ đọc</span>
      </header>
      {children}
    </section>
  );
}

export function ResourceState({
  kind,
  correlationId,
}: {
  readonly kind: 'empty' | 'forbidden' | 'unavailable';
  readonly correlationId?: string;
}) {
  const content = {
    empty: {
      title: 'Chưa có dữ liệu',
      description: 'API không trả về bản ghi nào trong phạm vi được cấp.',
    },
    forbidden: {
      title: 'Không đủ quyền truy cập',
      description:
        'Tài khoản hiện tại không có capability đọc cần thiết. Portal không thử tải dữ liệu.',
    },
    unavailable: {
      title: 'Tạm thời chưa thể tải dữ liệu',
      description:
        'Workforce API hoặc authorization authority chưa sẵn sàng. Hệ thống đã đóng quyền truy cập an toàn.',
    },
  } as const;
  return (
    <div className={`resource-state resource-state--${kind}`} role="status">
      <h2>{content[kind].title}</h2>
      <p>{content[kind].description}</p>
      {correlationId ? (
        <p>
          Mã đối chiếu: <code>{correlationId}</code>
        </p>
      ) : null}
    </div>
  );
}

export function StatusBadge({
  tone,
  children,
}: {
  readonly tone: 'positive' | 'neutral' | 'warning';
  readonly children: ReactNode;
}) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>;
}
