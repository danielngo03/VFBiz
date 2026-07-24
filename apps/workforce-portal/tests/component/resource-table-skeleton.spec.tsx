import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {ResourceTableSkeleton} from '@/components/feedback/resource-table-skeleton';

describe('ResourceTableSkeleton', () => {
  it('announces the pending resource without exposing decorative cells', () => {
    const {container} = render(
      <ResourceTableSkeleton columns={3} rows={2} label="Đang tải role" />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('Đang tải role');
    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(9);
  });
});
