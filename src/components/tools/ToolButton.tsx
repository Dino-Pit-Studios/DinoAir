import { memo, type CSSProperties } from 'react';

import type { ToolName } from '../../pages/tools/types';

export type ToolButtonProps = {
  tool: ToolName;
  label: string;
  isWired: boolean;
  isLoading: boolean;
  onClick: () => void;
};

const chipStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '6px 10px',
  borderRadius: 8,
  background: '#0f172a',
  border: '1px solid #1f2937',
  color: '#e5e7eb',
  fontSize: 13,
  lineHeight: 1,
  whiteSpace: 'nowrap',
  cursor: 'pointer',
};

const chipDisabledStyle: CSSProperties = {
  ...chipStyle,
  opacity: 0.6,
  cursor: 'not-allowed',
};

export default memo(function ToolButton({
  tool: _tool,
  label,
  isWired,
  isLoading,
  onClick,
}: ToolButtonProps) {
  const style = isWired ? (isLoading ? chipDisabledStyle : chipStyle) : chipDisabledStyle;
  return (
    <button
      onClick={onClick}
      disabled={!isWired || isLoading}
      style={style}
      aria-busy={isLoading || undefined}
      title={isWired ? 'Click to call backend' : 'Not yet wired (read-only phase)'}
    >
      {label}
      {isLoading ? ' …' : ''}
    </button>
  );
});
