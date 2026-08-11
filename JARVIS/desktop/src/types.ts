export type Project = {
  id: string;
  name: string;
  root_path?: string | null;
};

export type Session = {
  id: string;
  project_id?: string | null;
  title: string;
  updated_at: string;
};

export type DocumentFile = {
  id: string;
  display_name: string;
  relative_path: string;
  media_type: string;
  language?: string | null;
  size_bytes: number;
  status: string;
};

export type Citation = {
  document_id: string;
  file_name: string;
  source_path: string;
  chunk_id: string;
  page?: number | null;
  heading?: string | null;
  sheet?: string | null;
  cell_range?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  score?: number | null;
};

export type AgentAnswer = {
  session_id: string;
  message_id: string;
  answer: string;
  grounded: boolean;
  citations: Citation[];
  provider: string;
  tool_run_ids: string[];
  pending_approval_id?: string | null;
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  grounded: number;
  metadata_json: string;
  created_at: string;
};

export type BackendInfo = { host: string; port: number; ipc_token: string };

export type LocalSettingsStatus = {
  providers: Record<string, { available: boolean; reason: string }>;
  configured: Record<string, boolean>;
  models: { freemodel: string; openai: string; local: string };
  storage: string;
};

export type LocalSettingsDraft = {
  freemodel_api_key?: string;
  openai_api_key?: string;
  telegram_bot_token?: string;
  hf_token?: string;
  web_search_api_key?: string;
  google_access_token?: string;
  microsoft_access_token?: string;
  local_adapter_path?: string;
  freemodel_model?: string;
};
