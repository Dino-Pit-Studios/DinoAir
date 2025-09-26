import { useResponsive } from '../../hooks/useResponsive';

import type { CSSProperties, ReactNode } from 'react';

interface PageContainerProps {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}

/**
 * PageContainer provides a consistent wrapper for all page components.
 * It handles responsive padding and max-width constraints automatically.
 */
export default function PageContainer({
  children,
  className = '',
  style = {},
}: PageContainerProps) {
  const { isMobile } = useResponsive();

  const containerStyle: CSSProperties = {
    padding: isMobile ? '0 16px' : '0',
    maxWidth: '100%',
    ...style,
  };

  return (
    <div className={`page-container ${className}`.trim()} style={containerStyle}>
      {children}
    </div>
  );
}
