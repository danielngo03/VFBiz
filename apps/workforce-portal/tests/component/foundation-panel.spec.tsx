import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';
import {FoundationPanel} from '@/components/layout/foundation-panel';

describe('FoundationPanel', () => {
  it('communicates the backend authority and required capability', () => {
    render(
      <FoundationPanel
        eyebrow="Authorization"
        title="Role"
        description="Mô tả"
        requiredCapability="authorization.role.read"
      />,
    );

    expect(screen.getByRole('heading', {name: 'Role'})).toBeInTheDocument();
    expect(screen.getByText('authorization.role.read')).toBeInTheDocument();
    expect(screen.getByText('NestJS Authorization Platform')).toBeInTheDocument();
  });
});
