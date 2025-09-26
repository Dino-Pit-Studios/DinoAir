import { useEffect, useRef, useState } from 'react';

import { fileIndexStats } from '../lib/api';
import { backoffPoll } from '../lib/polling';

export interface UseRagStatsPollerInput {
  enabled: boolean;
  triggerKey?: string;
}

export interface UseRagStatsPollerOutput {
  message: string | null;
}

// New: explicit stats type and guard
interface RagStats {
  total_embeddings: number;
}

/**
 * Type guard to determine if the given value conforms to RagStats and is ready for vector search.
 * @param value - The value to check.
 * @returns True if the value is an object with a numeric total_embeddings property greater than 0.
 */
function isVectorSearchReady(value: unknown): value is RagStats {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const total = (value as { total_embeddings?: unknown }).total_embeddings;
  return typeof total === 'number' && total > 0;
}

/**
 * Starts a poller (when enabled) to check RAG index stats and emit a success message
 * once vector search should be available, mirroring prior startStatsPoller() behavior.
 */
export function useRagStatsPoller(input: UseRagStatsPollerInput): UseRagStatsPollerOutput {
  const { enabled, triggerKey } = input;
  const [message, setMessage] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!enabled) {
      // stop any existing poll
      abortRef.current?.abort();
      abortRef.current = null;
      return;
    }

    // Restart poller on trigger changes
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    /**
     * Starts an asynchronous polling loop to check file index statistics until
     * the vector/hybrid search is ready.
     *
     * @returns {Promise<void>} A promise that resolves when polling completes or is aborted.
     */
    const run = async () => {
      try {
        await backoffPoll(
          async () => {
            try {
              const stats = await fileIndexStats();
              // simplified conditional using type guard
              if (isVectorSearchReady(stats)) {
                setMessage('Vector/Hybrid search enabled');
                return true;
              }
            } catch {
              // ignore polling errors
            }
            return false;
          },
          (ready: boolean) => !ready,
          {
            interval: 1000,
            maxInterval: 10000,
            backoffMultiplier: 2,
            maxAttempts: 20,
          }
        );
      } catch {
        // aborted or exhausted attempts - noop
      }
    };

    run();

    return () => {
      ac.abort();
    };
  }, [enabled, triggerKey]);

  return { message };
}
