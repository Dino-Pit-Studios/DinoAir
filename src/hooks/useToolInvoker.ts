import { useCallback, useState } from 'react';

import { isHttp501Message } from '../lib/http';
import { isRagRemediationFail501, isRagSuccessEnvelope } from '../lib/rag';

import type { ToolHandler, ToolInvokeState, ToolName } from '../pages/tools/types';

const POLLER_TRIGGER_TOOLS = new Set<ToolName>([
  'rag_ingest_directory',
  'rag_ingest_files',
  'rag_generate_missing_embeddings',
]);

export interface UseToolInvokerInput {
  handlers: Record<ToolName, ToolHandler>;
}

export interface UseToolInvokerOutput {
  state: ToolInvokeState;
  invokeTool: (tool: ToolName, groupTitle: string) => Promise<void>;
  pollerTriggerKey: string | null;
}

/**
 * Custom hook to manage tool invocations and their state.
 *
 * @param input - An object containing handlers for each tool (UseToolInvokerInput).
 * @returns An object with the current invocation state, an invokeTool function, and a poller trigger key (UseToolInvokerOutput).
 */
export function useToolInvoker(input: UseToolInvokerInput): UseToolInvokerOutput {
  const { handlers } = input;

  const [state, setState] = useState<ToolInvokeState>({
    loadingTool: null,
    lastTool: null,
    lastResult: null,
    lastError: null,
    showRagRemediation: false,
  });

  const [pollerTriggerKey, setPollerTriggerKey] = useState<string | null>(null);

  const invokeTool = useCallback(
    async (tool: ToolName, groupTitle: string) => {
      setState(s => ({
        ...s,
        loadingTool: tool,
        lastTool: `${groupTitle} / ${tool}`,
        lastResult: null,
        lastError: null,
        showRagRemediation: false,
      }));

      try {
        const handler: ToolHandler = handlers[tool];
        const data = await handler(groupTitle);

        if (isRagRemediationFail501(data)) {
          setState(s => ({ ...s, showRagRemediation: true }));
        }

        setState(s => ({ ...s, lastResult: data }));

        if (POLLER_TRIGGER_TOOLS.has(tool) && isRagSuccessEnvelope(data)) {
          // trigger the poller; use timestamp for a stable, changing key
          setPollerTriggerKey(String(Date.now()));
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setState(s => ({ ...s, lastError: msg }));
        if (isHttp501Message(msg)) {
          setState(s => ({ ...s, showRagRemediation: true }));
        }
      } finally {
        setState(s => ({ ...s, loadingTool: null }));
      }
    },
    [handlers]
  );

  return {
    state,
    invokeTool,
    pollerTriggerKey,
  };
}
