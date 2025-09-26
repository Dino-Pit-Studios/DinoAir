import type { ReactNode } from 'react';

type BannerType = 'info' | 'success' | 'error' | 'warning';

interface BannerProps {
  type?: BannerType;
  children: ReactNode;
}

/**
 * Banner component for displaying notices with different styles based on type.
 *
 * @param {BannerType} type - The style type of the banner ('info', 'success', 'warning', 'error'). Defaults to 'info'.
 * @param {React.ReactNode} children - Content to display inside the banner.
 * @returns {JSX.Element} The rendered banner element.
 */
export default function Banner({ type = 'info', children }: BannerProps) {
  const palette: Record<BannerType, { bg: string; color: string; border: string }> = {
    info: { bg: 'rgba(59,130,246,0.15)', color: '#bfdbfe', border: '#3b82f6' },
    success: {
      bg: 'rgba(16,185,129,0.15)',
      color: '#bbf7d0',
      border: '#10b981',
    },
    warning: {
      bg: 'rgba(234,179,8,0.15)',
      color: '#fde68a',
      border: '#eab308',
    },
    error: { bg: 'rgba(239,68,68,0.15)', color: '#fecaca', border: '#ef4444' },
  };

  const { bg, color, border } = palette[type];

  return (
    <div
      className='banner'
      role='status'
      style={{
        background: bg,
        color,
        border: `1px solid ${border}`,
        borderLeft: `3px solid ${border}`,
        borderRadius: 8,
        padding: 12,
        margin: '8px 0',
        fontSize: 14,
      }}
    >
      {children}
    </div>
  );
}
