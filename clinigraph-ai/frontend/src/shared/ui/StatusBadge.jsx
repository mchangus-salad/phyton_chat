export function StatusBadge({ tone, children }) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>;
}