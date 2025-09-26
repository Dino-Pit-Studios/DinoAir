import React, { memo, useCallback, useMemo, useState, type CSSProperties } from 'react';

import Banner from '../components/common/Banner';
import Button from '../components/common/Button';
import Card from '../components/common/Card';
import OtherToolsPage from '../components/icons/OtherToolsPage';
import PageContainer from '../components/layout/PageContainer';
import PageHeader from '../components/layout/PageHeader';
import { fileIndexStats, ragApi, searchApi, type RagEnvelope } from '../lib/api';
import { isHttp501Message } from '../lib/http';

type ToolGroup = {
  title: string;
  module?: string;
  tools: string[];
};

const toolGroups: ToolGroup[] = [
  {
    title: 'Core utilities',
    tools: [
      'add_two_numbers',
      'get_current_time',
      'list_directory_contents',
      'read_text_file',
      'execute_system_command',
      'create_json_data',
    ],
  },
  {
    title: 'Notes management',
    module: 'notes_tool.py',
    tools: [
      'create_note',
      'read_note',
      'update_note',
      'delete_note',
      'search_notes',
      'list_all_notes',
      'get_notes_by_tag',
      'get_all_tags',
    ],
  },
  {
    title: 'File search',
    module: 'file_search_tool.py',
    tools: ['keyword_search', 'vector_search', 'hybrid_search'],
  },
  {
    title: 'RAG operations',
    tools: [
      'rag_ingest_directory',
      'rag_ingest_files',
      'rag_generate_missing_embeddings',
      'rag_context',
    ],
  },
  {
    title: 'Project management',
    module: 'projects_tool.py',
    tools: [
      'create_project',
      'get_project',
      'update_project',
      'delete_project',
      'list_all_projects',
      'search_projects',
      'get_projects_by_status',
      'get_project_statistics',
      'get_project_tree',
    ],
  },
];

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

type ToolHandler = (groupTitle: string) => Promise<unknown>;

/**
 * Checks whether the provided data is a successful RAG envelope.
 * @param data - The data to check.
 * @returns True if the data is a RagEnvelope with success true; otherwise, false.
 */
function isRagSuccessEnvelope(data: unknown): data is RagEnvelope {
  return (
    data !== null &&
    typeof data === 'object' &&
    'success' in data &&
    (data as { success: unknown }).success === true
  );
}

/**
 * Checks if the given data indicates a RAG remediation failure with status code 501.
 *
 * @param data - The input data to evaluate, expected to have a 'success' property and optionally a 'code' property.
 * @returns True if success is false and code is 501, otherwise false.
 */
function isRagRemediationFail501(data: unknown): boolean {
  /**
   * Checks if the given data represents an HTTP 501 response message.
   * @param data - The data to evaluate, expected to be an object with optional `success` and `code` properties.
   * @returns True if the data indicates a failed request with status code 501.
   */
  if (!data || typeof data !== 'object' || !('success' in data)) return false;
  const responseData = data as { success?: unknown; code?: unknown };
  const code = typeof responseData.code === 'number' ? responseData.code : undefined;
  return responseData.success === false && code === 501;
}
/**
 * Starts a polling process that checks file index statistics periodically.
 * It attempts up to 20 times, increasing delay up to 10000ms, and stops after 60 seconds.
 *
 * @param setMessage - Function callback to update the status message.
 * @returns {Promise<void>} Promise that resolves when polling completes or embeddings are found.
 */
async function startStatsPoller(setMessage: (msg: string) => void): Promise<void> {
  let delay = 1000;
  let elapsed = 0;
  for (let i = 0; i < 20; i++) {
    try {
      const stats = await fileIndexStats();
      if (stats && typeof stats.total_embeddings === 'number' && stats.total_embeddings > 0) {
        setMessage('Vector/Hybrid search enabled');
        return;
      }
    } catch {
      // ignore polling errors
    }
    await new Promise(r => setTimeout(r, delay));
    elapsed += delay;
    if (delay < 10000) {
      delay = Math.min(10000, delay * (delay < 4000 ? 2 : 1.5));
    }
    if (elapsed >= 60000) break;
  }
}

const POLLER_TRIGGER_TOOLS = new Set<string>([
  'rag_ingest_directory',
  'rag_ingest_files',
  'rag_generate_missing_embeddings',
]);

/**
 * Creates a handler function for performing searches of the given type via the provided API call.
 *
 * @param searchType - A string describing the type of search to perform.
 * @param apiCall - A function that takes an object with query and top_k, and returns a Promise of the search result.
 * @returns A ToolHandler function that prompts the user for query and top_k, then calls the API.
 */
function createSearchHandler(
  searchType: string,
  apiCall: (params: { query: string; top_k: number }) => Promise<unknown>
): ToolHandler {
  return async () => {
    const query = (await customPrompt(`${searchType} query:`, '')) || '';
    const topkStr = (await customPrompt('top_k (default 10):', '10')) || '10';
    const top_k = Math.max(1, Number(topkStr) || 10);
    return apiCall({ query, top_k });
  };
}

const HANDLERS: Record<string, ToolHandler> = {
  // Core
  get_current_time: async () => {
    return core.getCurrentTime();
  },
  list_directory_contents: async () => {
    return core.listDirectory('/');
  },

  // Notes (GET)
  list_all_notes: async () => {
    return notes.listAllNotes();
  },
  search_notes: async () => {
    return notes.searchNotes('test');
  },
  get_all_tags: async () => {
    return notes.getAllTags();
  },
  get_notes_by_tag: async () => {
    return notes.getNotesByTag('general');
  },

  // File Search via backend /file-search/*
  keyword_search: createSearchHandler('Keyword', params => searchApi.keyword(params)),
  vector_search: createSearchHandler('Vector', params => searchApi.vector(params)),
  hybrid_search: createSearchHandler('Hybrid', params =>
    searchApi.hybrid({ ...params, vector_weight: 0.5, keyword_weight: 0.5 })
  ),

  // RAG operations via backend /rag/*
  rag_ingest_directory: async () => {
    const directory = (await customPrompt('Directory to ingest:', ''))?.trim();
    if (!directory) throw new Error('Cancelled by user');
    const recursiveStr =
      (await customPrompt('Recursive? (true/false, default true):', 'true')) || 'true';
    const recursive = recursiveStr.toLowerCase() !== 'false';
    const typesRaw = (await customPrompt('File types (comma separated, optional):', '')) || '';
    const file_types = typesRaw
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);
    const body: { directory_path: string; recursive?: boolean; file_types?: string[] } = {
      directory_path: directory,
      recursive,
    };
    if (file_types.length) body.file_types = file_types;
    return ragApi.ingestDirectory(body);
  },
  rag_ingest_files: async () => {
    const pathsRaw = customPrompt('Paths to ingest (comma separated):', '') || '';
    const paths = pathsRaw
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);
    if (!paths.length) throw new Error('Cancelled by user');
    return ragApi.ingestFiles({ paths });
  },
  rag_generate_missing_embeddings: async () => {
    const bs = (await customPrompt('Batch size:', '32')) || '32';
    const batch_size = Math.max(1, Number(bs) || 32);
    return ragApi.generateMissingEmbeddings({ batch_size });
  },
  rag_context: async () => {
    const query = (await customPrompt('Context query:', '')) || '';
    const topkStr = (await customPrompt('top_k (default 5):', '5')) || '5';
    const top_k = Math.max(1, Number(topkStr) || 5);
    return ragApi.context({ query, top_k });
  },

  // Projects (GET)
  list_all_projects: async () => {
    return projects.listAll();
  },
  get_project: async () => {
    return projects.get(1);
  },
  search_projects: async () => {
    return projects.search('demo');
  },
  get_projects_by_status: async () => {
    return projects.byStatus('active');
  },
  get_project_statistics: async () => {
    return projects.getStats();
  },
  get_project_tree: async () => {
    return projects.getTree(1);
  },

  // Mutations (prompt-driven)
  add_two_numbers: async () => {
    const firstNumberInput = await customPrompt('Enter first number (a):', '1');
    const secondNumberInput = await customPrompt('Enter second number (b):', '2');
    if (firstNumberInput === null || secondNumberInput === null)
      throw new Error('Cancelled by user');
    const firstNumber = Number(firstNumberInput);
    const secondNumber = Number(secondNumberInput);
    if (Number.isNaN(firstNumber) || Number.isNaN(secondNumber))
      throw new Error('Inputs must be numbers');
    const userConfirmed = await customConfirm(
      `Call add_two_numbers with a=${firstNumber}, b=${secondNumber}?`
    );
    if (!userConfirmed) throw new Error('Cancelled by user');
    return core.addTwoNumbers(firstNumber, secondNumber);
  },
  create_note: async () => {
    const title = customPrompt('Note title:', 'Quick note') || '';
    const content = customPrompt('Note content:', 'Hello world') || '';
    const tagsRaw = customPrompt('Tags (comma separated, optional):', '') || '';
    const tags = tagsRaw
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);
    const ok = customConfirm(`Create note "${title}" with ${tags.length} tag(s)?`);
    if (!ok) throw new Error('Cancelled by user');
    return notes.createNote({
      title,
      content,
      tags: tags.length ? tags : undefined,
    });
  },
};

/**
 * Generates a default response object for a tool when no further input is provided.
 * @param {string} groupTitle - The title of the tool group.
 * @param {string} tool - The identifier of the tool.
 * @returns {{ note: string; tool: string; group: string; next_steps: string; }} The default response object including notes and next steps.
 */
function defaultToolResponse(groupTitle: string, tool: string) {
  return {
    note: 'This tool requires additional input or is not yet wired. Use Settings/Pages for richer forms as a next step.',
    tool,
    group: groupTitle,
    next_steps: 'Implement full POST/PUT/DELETE flows with dedicated forms and optimistic updates.',
  };
}

type ToolButtonProps = {
  tool: string;
  isWired: boolean;
  isLoading: boolean;
  onClick: () => void;
};

const ToolButton = memo(function ToolButton({
  tool,
  isWired,
  isLoading,
  onClick,
}: ToolButtonProps) {
  const baseStyle = isWired ? chipStyle : chipDisabledStyle;
  const style = isLoading ? chipDisabledStyle : baseStyle;
  return (
    <button
      onClick={onClick}
      disabled={!isWired || isLoading}
      style={style}
      title={isWired ? 'Click to call backend' : 'Not yet wired (read-only phase)'}
    >
      {tool}
      {isLoading ? ' …' : ''}
    </button>
  );
});

type ToolGroupCardProps = {
  group: ToolGroup;
  wiredReadOnlyTools: Set<string>;
  loadingTool: string | null;
  onInvoke: (groupTitle: string, tool: string) => void;
};

const ToolGroupCard = memo(function ToolGroupCard({
  group,
  wiredReadOnlyTools,
  loadingTool,
  onInvoke,
}: ToolGroupCardProps) {
  const toolClickHandlers = React.useMemo(() => {
    const handlers: Record<string, () => void> = {};
    group.tools.forEach(tool => {
      handlers[tool] = () => {
        if (wiredReadOnlyTools.has(tool)) {
          onInvoke(group.title, tool);
        }
      };
    });
    return handlers;
  }, [group.tools, wiredReadOnlyTools, onInvoke, group.title]);

  return (
    <Card key={group.title} title={`${group.title} (${group.tools.length})`}>
      {group.module && (
        <div style={{ marginBottom: 8, color: '#9ca3af', fontSize: 12 }}>from {group.module}</div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {group.tools.map(tool => {
          const isWired = wiredReadOnlyTools.has(tool);
          const isLoading = loadingTool === tool;
          return (
            <ToolButton
              key={tool}
              tool={tool}
              isWired={isWired}
              isLoading={isLoading}
              onClick={toolClickHandlers[tool]}
            />
          );
        })}
      </div>
    </Card>
  );
});

type RagRemediationBannerProps = {
  onInvoke: (groupTitle: string, tool: string) => void;
};

const RagRemediationBanner = memo(function RagRemediationBanner({
  onInvoke,
}: RagRemediationBannerProps) {
  const handleIngestClick = useCallback(
    () => onInvoke('RAG operations', 'rag_ingest_files'),
    [onInvoke]
  );
  const handleGenerateClick = useCallback(
    () => onInvoke('RAG operations', 'rag_generate_missing_embeddings'),
    [onInvoke]
  );

  return (
    <Banner type='warning'>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
        }}
      >
        <div>
          Vector/Hybrid search unavailable. Ingest files and generate missing embeddings to enable
          RAG features.
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant='secondary' onClick={handleIngestClick}>
            Ingest files…
          </Button>
          <Button variant='secondary' onClick={handleGenerateClick}>
            Generate embeddings
          </Button>
        </div>
      </div>
    </Banner>
  );
});

type ResultCardProps = {
  lastTool: string | null;
  lastError: string | null;
  lastResult: unknown;
};

const ResultCard = memo(function ResultCard({ lastTool, lastError, lastResult }: ResultCardProps) {
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

/**
 * ToolsPage component renders the UI for invoking various tools,
 * manages tool invocation state, displays results, and handles RAG remediation.
 *
 * @returns JSX.Element The rendered Tools page component.
 */
export default function ToolsPage() {
  const [loadingTool, setLoadingTool] = useState<string | null>(null);
  const [lastTool, setLastTool] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<unknown>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const [showRagRemediation, setShowRagRemediation] = useState(false);
  const [ragStatusMessage, setRagStatusMessage] = useState<string | null>(null);

  const wiredReadOnlyTools = useMemo(
    () =>
      new Set<string>([
        // Core (GET only)
        'get_current_time',
        'list_directory_contents',
        // Notes (GET)
        'search_notes',
        'list_all_notes',
        'get_notes_by_tag',
        'get_all_tags',
        // File search
        'keyword_search',
        'vector_search',
        'hybrid_search',
        // Projects (GET)
        'list_all_projects',
        'get_project',
        'search_projects',
        'get_projects_by_status',
        'get_project_statistics',
        'get_project_tree',
        // RAG operations
        'rag_ingest_directory',
        'rag_ingest_files',
        'rag_generate_missing_embeddings',
        'rag_context',
        // Mutations (enabled with prompts + confirmations)
        'add_two_numbers',
        'create_note',
      ]),
    []
  );

  const invokeTool = useCallback(async (groupTitle: string, tool: string) => {
    setLoadingTool(tool);
    setLastTool(`${groupTitle} / ${tool}`);
    setLastResult(null);
    setLastError(null);
    setShowRagRemediation(false);

    try {
      const handler: ToolHandler =
        HANDLERS[tool] || (gt => Promise.resolve(defaultToolResponse(gt, tool)));
      const data = await handler(groupTitle);

      if (isRagRemediationFail501(data)) {
        setShowRagRemediation(true);
      }

      setLastResult(data);

      if (POLLER_TRIGGER_TOOLS.has(tool) && isRagSuccessEnvelope(data)) {
        // Launch async poller to watch for vector availability
        startStatsPoller(setRagStatusMessage);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setLastError(msg);
      if (isHttp501Message(msg)) {
        setShowRagRemediation(true);
      }
    } finally {
      setLoadingTool(null);
    }
  }, []);

  return (
    <PageContainer className='tools-page'>
      <PageHeader icon={<OtherToolsPage width={20} height={20} />} title='Tools' />

      <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {toolGroups.map(group => (
          <ToolGroupCard
            key={group.title}
            group={group}
            wiredReadOnlyTools={wiredReadOnlyTools}
            loadingTool={loadingTool}
            onInvoke={invokeTool}
          />
        ))}
      </section>

      <section style={{ marginTop: 12 }}>
        {ragStatusMessage && <Banner type='success'>{ragStatusMessage}</Banner>}
        {showRagRemediation && <RagRemediationBanner onInvoke={invokeTool} />}

        <ResultCard lastTool={lastTool} lastError={lastError} lastResult={lastResult} />
      </section>
    </PageContainer>
  );
}
