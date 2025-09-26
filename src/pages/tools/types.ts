// Types for Tools page refactor

export type ToolName =
  | 'get_current_time'
  | 'list_directory_contents'
  | 'read_text_file'
  | 'execute_system_command'
  | 'create_json_data'
  | 'add_two_numbers'
  | 'create_note'
  | 'read_note'
  | 'update_note'
  | 'delete_note'
  | 'search_notes'
  | 'list_all_notes'
  | 'get_notes_by_tag'
  | 'get_all_tags'
  | 'keyword_search'
  | 'vector_search'
  | 'hybrid_search'
  | 'rag_ingest_directory'
  | 'rag_ingest_files'
  | 'rag_generate_missing_embeddings'
  | 'rag_context'
  | 'create_project'
  | 'get_project'
  | 'update_project'
  | 'delete_project'
  | 'list_all_projects'
  | 'search_projects'
  | 'get_projects_by_status'
  | 'get_project_statistics'
  | 'get_project_tree';

export interface ToolGroupTool {
  key: ToolName;
  label: string;
  readOnly?: boolean; // Indicates enabled/wired in read-only phase
}

export interface ToolGroup {
  title: string;
  module?: string; // Optional origin module display (e.g., "notes_tool.py")
  tools: ToolGroupTool[];
}

export type ToolHandler = (groupTitle: string) => Promise<unknown>;

export interface ToolInvokeState {
  loadingTool: ToolName | null;
  lastTool: string | null;
  lastResult: unknown;
  lastError: string | null;
  showRagRemediation: boolean;
}
