import { useMemo } from 'react';

import { toolGroups } from '../pages/tools/config';

import type { ToolName } from '../pages/tools/types';

/**
 * Derives the set of read-only (wired) tools from the single source of truth config.
 */
export function useWiredTools(): Set<ToolName> {
  return useMemo(() => {
    const set = new Set<ToolName>();
    for (const group of toolGroups) {
      for (const t of group.tools) {
        if (t.readOnly) {
          set.add(t.key);
        }
      }
    }
    return set;
  }, []);
}
