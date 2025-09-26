import { ToolGroup } from './types';

/**
 * Single source of truth for Tools page groups and tool enablement.
 * - label: display text on the chip
 * - readOnly: when true, the tool is wired/enabled (matches previous UI enablement)
 *             when false/omitted, the chip renders disabled (as before)
 */
export const toolGroups: ToolGroup[] = [
  {
    title: 'Core utilities',
    tools: [
      { key: 'add_two_numbers', label: 'add_two_numbers', readOnly: true },
      { key: 'get_current_time', label: 'get_current_time', readOnly: true },
      {
        key: 'list_directory_contents',
        label: 'list_directory_contents',
        readOnly: true,
      },
      { key: 'read_text_file', label: 'read_text_file' },
      { key: 'execute_system_command', label: 'execute_system_command' },
      { key: 'create_json_data', label: 'create_json_data' },
    ],
  },
  {
    title: 'Notes management',
    module: 'notes_tool.py',
    tools: [
      { key: 'create_note', label: 'create_note', readOnly: true },
      { key: 'read_note', label: 'read_note' },
      { key: 'update_note', label: 'update_note' },
      { key: 'delete_note', label: 'delete_note' },
      { key: 'search_notes', label: 'search_notes', readOnly: true },
      { key: 'list_all_notes', label: 'list_all_notes', readOnly: true },
      { key: 'get_notes_by_tag', label: 'get_notes_by_tag', readOnly: true },
      { key: 'get_all_tags', label: 'get_all_tags', readOnly: true },
    ],
  },
  {
    title: 'File search',
    module: 'file_search_tool.py',
    tools: [
      { key: 'keyword_search', label: 'keyword_search', readOnly: true },
      { key: 'vector_search', label: 'vector_search', readOnly: true },
      { key: 'hybrid_search', label: 'hybrid_search', readOnly: true },
    ],
  },
  {
    title: 'RAG operations',
    tools: [
      {
        key: 'rag_ingest_directory',
        label: 'rag_ingest_directory',
        readOnly: true,
      },
      { key: 'rag_ingest_files', label: 'rag_ingest_files', readOnly: true },
      {
        key: 'rag_generate_missing_embeddings',
        label: 'rag_generate_missing_embeddings',
        readOnly: true,
      },
      { key: 'rag_context', label: 'rag_context', readOnly: true },
    ],
  },
  {
    title: 'Project management',
    module: 'projects_tool.py',
    tools: [
      { key: 'create_project', label: 'create_project' },
      { key: 'get_project', label: 'get_project', readOnly: true },
      { key: 'update_project', label: 'update_project' },
      { key: 'delete_project', label: 'delete_project' },
      { key: 'list_all_projects', label: 'list_all_projects', readOnly: true },
      { key: 'search_projects', label: 'search_projects', readOnly: true },
      {
        key: 'get_projects_by_status',
        label: 'get_projects_by_status',
        readOnly: true,
      },
      {
        key: 'get_project_statistics',
        label: 'get_project_statistics',
        readOnly: true,
      },
      { key: 'get_project_tree', label: 'get_project_tree', readOnly: true },
    ],
  },
];
