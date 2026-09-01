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

export type RagAnswer = {
  session_id: string;
  message_id: string;
  answer: string;
  grounded: boolean;
  citations: Citation[];
  provider: string;
  fallback: boolean;
  source_selector: string;
  retrieved_chunks: number;
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
  models: { freemodel: string; openai: string };
  storage: string;
};

export type LocalSettingsDraft = {
  freemodel_api_key?: string;
  openai_api_key?: string;
  hf_token?: string;
  freemodel_model?: string;
};
