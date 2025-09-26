import type { ReactNode } from 'react';

interface MetricTileProps {
  label: string;
  value: string | number;
  icon?: ReactNode;
}

/**
 * Renders a styled metric tile component displaying a label, a value, and an optional icon.
 *
 * @param {Object} props - The props for the MetricTile component.
 * @param {string} props.label - The label text for the metric.
 * @param {string|number} props.value - The value to display in the tile.
 * @param {React.ReactNode} [props.icon] - Optional icon element displayed alongside the metric.
 * @returns {JSX.Element} The rendered MetricTile component.
 */
export default function MetricTile({ label, value, icon }: MetricTileProps) {
  return (
    <div
      className='metric-tile'
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        background: '#0f172a',
        border: '1px solid #1f2937',
        borderRadius: 10,
        padding: '12px 16px',
        color: '#e5e7eb',
        minWidth: 160,
      }}
    >
      <div style={{ color: '#60a5fa' }}>{icon ?? null}</div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <span style={{ fontSize: 12, color: '#9ca3af' }}>{label}</span>
        <strong style={{ fontSize: 18, color: '#e5e7eb' }}>{value}</strong>
      </div>
    </div>
  );
}
