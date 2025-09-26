import { ragApi, searchApi } from '../../lib/api';
import { confirmAction, promptString } from '../../lib/prompts';
import * as core from '../../services/core';
import * as notes from '../../services/notes';
import * as projects from '../../services/projects';

import type { ToolHandler, ToolName } from './types';

/**
 * Default response for unwired tools (preserves previous behavior)
 */
export function defaultToolResponse(groupTitle: string, tool: ToolName) {
  return {
    note: 'This tool requires additional input or is not yet wired. Use Settings/Pages for richer forms as a next step.',
    tool,
    group: groupTitle,
    next_steps: 'Implement full POST/PUT/DELETE flows with dedicated forms and optimistic updates.',
  };
}

export const HANDLERS: Record<ToolName, ToolHandler | undefined> = {
  // Core utilities (wired)
  get_current_time: async () => {
    return core.getCurrentTime();
  },
  list_directory_contents: async () => {
    return core.listDirectory('/');
  },
  add_two_numbers: async () => {
    const aRaw = await promptString('Enter first number (a):', '1');
    const bRaw = await promptString('Enter second number (b):', '2');
    if (aRaw === null || bRaw === null) throw new Error('Cancelled by user');
    const a = Number(aRaw);
    const b = Number(bRaw);
    if (Number.isNaN(a) || Number.isNaN(b)) {
      throw new Error('Inputs must be numbers');
    }
    const ok = await confirmAction(`Call add_two_numbers with a=${a}, b=${b}?`);
    if (!ok) throw new Error('Cancelled by user');
    return core.addTwoNumbers(a, b);
  },

  // Unwired in original page (fallback)
  read_text_file: undefined,
  execute_system_command: undefined,
  create_json_data: undefined,

  // Notes (wired GET + create)
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
  create_note: async () => {
    const title = (await promptString('Note title:', 'Quick note')) ?? '';
    const content = (await promptString('Note content:', 'Hello world')) ?? '';
    const tagsRaw = (await promptString('Tags (comma separated, optional):', '')) ?? '';
    const tags = tagsRaw
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);
    const ok = await confirmAction(`Create note "${title}" with ${tags.length} tag(s)?`);
    if (!ok) throw new Error('Cancelled by user');
    return notes.createNote({
      title,
      content,
      tags: tags.length ? tags : undefined,
    });
  },

  // Unwired in original page (fallback)
  read_note: undefined,
  update_note: undefined,
  delete_note: undefined,

  // File Search (wired)
  keyword_search: async () => {
    const query = (await promptString('Keyword query:', '')) ?? '';
    const topkRaw = (await promptString('top_k (default 10):', '10')) ?? '10';
    const top_k = Math.max(1, Number(topkRaw) || 10);
    return searchApi.keyword({ query, top_k });
  },
  vector_search: async () => {
    const query = (await promptString('Vector query:', '')) ?? '';
    const topkRaw = (await promptString('top_k (default 10):', '10')) ?? '10';
    const top_k = Math.max(1, Number(topkRaw) || 10);
    return searchApi.vector({ query, top_k });
  },
  hybrid_search: async () => {
    const query = (await promptString('Hybrid query:', '')) ?? '';
    const topkRaw = (await promptString('top_k (default 10):', '10')) ?? '10';
    const top_k = Math.max(1, Number(topkRaw) || 10);
    return searchApi.hybrid({
      query,
      top_k,
      vector_weight: 0.5,
      keyword_weight: 0.5,
    });
  },

  // RAG operations (wired)
  rag_ingest_directory: async () => {
    const directory = (await promptString('Directory to ingest:', ''))?.trim();
    if (!directory) throw new Error('Cancelled by user');
    const recursiveStr =
      (await promptString('Recursive? (true/false, default true):', 'true')) ?? 'true';
    const recursive = recursiveStr.toLowerCase() !== 'false';
    const typesRaw = (await promptString('File types (comma separated, optional):', '')) ?? '';
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
    const pathsRaw = (await promptString('Paths to ingest (comma separated):', '')) ?? '';
    const paths = pathsRaw
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);
    if (!paths.length) throw new Error('Cancelled by user');
    return ragApi.ingestFiles({ paths });
  },
  rag_generate_missing_embeddings: async () => {
    const bsMaybe = await promptString('Batch size:', '32');
    const bs = bsMaybe ?? '32';
    const batch_size = Math.max(1, Number(bs) || 32);
    return ragApi.generateMissingEmbeddings({ batch_size });
  },
  rag_context: async () => {
    const query = (await promptString('Context query:', '')) ?? '';
    const topkRaw = (await promptString('top_k (default 5):', '5')) ?? '5';
    const top_k = Math.max(1, Number(topkRaw) || 5);
    return ragApi.context({ query, top_k });
  },

  // Projects (wired GET)
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

  // Unwired in original page (fallback)
  create_project: undefined,
  update_project: undefined,
  delete_project: undefined,
};
export const RESOLVED_HANDLERS: Record<ToolName, ToolHandler> = Object.fromEntries(
  (Object.entries(HANDLERS) as [ToolName, ToolHandler | undefined][]).map(([k, v]) => [
    k,
    v ?? ((groupTitle: string) => Promise.resolve(defaultToolResponse(groupTitle, k))),
  ])
) as Record<ToolName, ToolHandler>;
