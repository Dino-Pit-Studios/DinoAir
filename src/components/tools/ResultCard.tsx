import { memo } from 'react';

import Card from '../common/Card';

export type ResultCardProps = {
  lastTool: string | null;
  lastError: string | null;
  lastResult: unknown;
};

export default memo(function ResultCard({ lastTool, lastError, lastResult }: ResultCardProps) {
  return (
    <Card title='Last result'>
      {!lastTool && (
        <div style={{ color: '#9ca3af', fontSize: 13 }}>
          Click a wired tool to validate connectivity.
        </div>
      )}
      {lastTool && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 13, color: '#9ca3af' }}>Tool: {lastTool}</div>
          {lastError ? (
            <pre
              style={{
                margin: 0,
                padding: 8,
                background: '#0b1022',
                border: '1px solid #1f2937',
                borderRadius: 6,
                color: '#fecaca',
                maxHeight: 240,
                overflow: 'auto',
              }}
            >
              {String(lastError)}
            </pre>
          ) : (
            <pre
              style={{
                margin: 0,
                padding: 8,
                background: '#0b1022',
                border: '1px solid #1f2937',
                borderRadius: 6,
                color: '#e5e7eb',
                maxHeight: 240,
                overflow: 'auto',
              }}
            >
              {JSON.stringify(lastResult, null, 2)}
            </pre>
          )}
        </div>
      )}
    </Card>
  );
});
