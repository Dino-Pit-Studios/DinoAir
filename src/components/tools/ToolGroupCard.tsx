import React, { memo } from 'react';

import Card from '../common/Card';

import ToolButton from './ToolButton';

import type { ToolGroup, ToolName } from '../../pages/tools/types';

export type ToolGroupCardProps = {
  group: ToolGroup;
  wiredReadOnlyTools: Set<ToolName>;
  loadingTool: ToolName | null;
  onInvoke: (groupTitle: string, tool: ToolName) => void;
};

export default memo(function ToolGroupCard({
  group,
  wiredReadOnlyTools,
  loadingTool,
  onInvoke,
}: ToolGroupCardProps) {
  const handleInvoke = React.useCallback(
    (title: string, key: string) => {
      if (wiredReadOnlyTools.has(key)) {
        onInvoke(title, key);
      }
    },
    [wiredReadOnlyTools, onInvoke]
  );

  const clickHandlers = React.useMemo(() => {
    const handlers: Record<string, () => void> = {};
    group.tools.forEach(t => {
      handlers[t.key] = () => handleInvoke(group.title, t.key);
    });
    return handlers;
  }, [group.tools, group.title, handleInvoke]);

  return (
    <Card key={group.title} title={`${group.title} (${group.tools.length})`}>
      {group.module && (
        <div style={{ marginBottom: 8, color: '#9ca3af', fontSize: 12 }}>from {group.module}</div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {group.tools.map(t => {
          const isWired = wiredReadOnlyTools.has(t.key);
          const isLoading = loadingTool === t.key;
          return (
            <ToolButton
              key={t.key}
              tool={t.key}
              label={t.label}
              isWired={isWired}
              isLoading={isLoading}
              onClick={clickHandlers[t.key]}
            />
          );
        })}
      </div>
    </Card>
  );
});
