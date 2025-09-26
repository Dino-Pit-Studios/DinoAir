import type { CSSProperties, ReactNode } from 'react';

interface PageHeaderProps {
  /** The icon component to display */
  icon?: ReactNode;
  /** The page title */
  title: string;
  /** Optional subtitle or description */
  subtitle?: string;
  /** Optional actions or controls to display on the right side */
  actions?: ReactNode;
  /** Additional CSS classes */
  className?: string;
  /** Additional inline styles */
  style?: CSSProperties;
  /** ARIA label for the header */
  ariaLabel?: string;
}

/**
 * PageHeader provides a consistent header structure for all page components.
 * It displays an icon, title, optional subtitle, and optional action buttons.
 */
export default function PageHeader({
  icon,
  title,
  subtitle,
  actions,
  className = '',
  style = {},
  ariaLabel,
}: PageHeaderProps) {
  const headerStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
    flexWrap: 'wrap',
    ...style,
  };

  return (
    <header
      className={`page-header ${className}`.trim()}
      style={headerStyle}
      role='banner'
      aria-label={ariaLabel || `${title} page header`}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
        {icon && (
          <span className='page-header-icon' aria-hidden='true'>
            {icon}
          </span>
        )}
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>{title}</h1>
          {subtitle && (
            <p style={{ margin: '4px 0 0 0', fontSize: 14, color: '#9ca3af' }}>{subtitle}</p>
          )}
        </div>
      </div>
      {actions && (
        <div
          className='page-header-actions'
          style={{ display: 'flex', alignItems: 'center', gap: 8 }}
        >
          {actions}
        </div>
      )}
    </header>
  );
}
