import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {
  ResourcePage,
  ResourceState,
  StatusBadge,
} from '@/components/layout/resource-page';

describe('ResourcePage', () => {
  it('announces that the current bounded views are read-only', () => {
    render(
      <ResourcePage
        eyebrow="Authorization"
        title="Role và capability"
        description="Dữ liệu thật từ API."
      >
        <StatusBadge tone="positive">Đang hoạt động</StatusBadge>
      </ResourcePage>,
    );

    expect(screen.getByRole('heading', {name: 'Role và capability'}))
      .toBeInTheDocument();
    expect(screen.getByText('Chỉ đọc')).toBeInTheDocument();
    expect(screen.getByText('Đang hoạt động')).toBeInTheDocument();
  });

  it('renders a fail-closed state without exposing upstream details', () => {
    render(
      <ResourceState
        kind="unavailable"
        correlationId="019f8d8e-5a47-7c2e-8c26-43f33039bd08"
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent(
      'Hệ thống đã đóng quyền truy cập an toàn.',
    );
    expect(screen.getByRole('status')).toHaveTextContent('Mã đối chiếu');
  });
});
