import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders children text', () => {
    render(<StatusBadge tone="success">Active</StatusBadge>);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('applies the correct tone modifier class', () => {
    render(<StatusBadge tone="error">Error</StatusBadge>);
    const badge = screen.getByText('Error');
    expect(badge).toHaveClass('status-badge--error');
  });

  it('always includes the base status-badge class', () => {
    render(<StatusBadge tone="warning">Warning</StatusBadge>);
    expect(screen.getByText('Warning')).toHaveClass('status-badge');
  });

  it('renders as a span element', () => {
    const { container } = render(<StatusBadge tone="info">Info</StatusBadge>);
    expect(container.firstChild.tagName).toBe('SPAN');
  });
});
