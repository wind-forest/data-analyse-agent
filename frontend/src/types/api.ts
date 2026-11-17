export interface Session {
  id: string;
  title: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

export type FileStatus = "uploading" | "validating" | "ready" | "failed";

export interface DataFile {
  id: string;
  session_id: string;
  original_name: string;
  size: number;
  sha256: string;
  mime: string | null;
  status: FileStatus;
  error: string | null;
  created_at: string;
}

export interface ToolHistory {
  call_id?: string | null;
  run_id?: string | null;
  tool: string;
  params: Record<string, unknown>;
  hash?: string;
  status?: "running" | "success" | "failed";
  summary?: string;
  duration_ms?: number;
  error?: string | null;
  artifact_ids?: string[];
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls_json: ToolHistory[] | null;
  finish_reason: string | null;
  created_at: string;
}

export type ArtifactType = "chart" | "table" | "model";

export interface Artifact {
  id: string;
  run_id: string;
  message_id: string | null;
  type: ArtifactType;
  payload_json: Record<string, unknown> | null;
  file_path: string | null;
  created_at: string;
}

export interface AppConfig {
  default_model: string;
  allowed_models: string[];
  max_upload_size_mb: number;
  custom_code_available: boolean;
}

export interface MessagePayload {
  content: string;
  file_ids: string[];
  model?: string;
  allow_custom_code: boolean;
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

export interface User {
  id: string;
  username: string;
  display_name: string | null;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface CaptchaResponse {
  captcha_id: string;
  image: string;
  hint: string;
}

export interface MeResponse {
  user: User | null;
  anon_sessions_remaining: number;
  anon_messages_remaining_per_session: number;
}

export interface LoginRequest {
  username: string;
  password: string;
  captcha_id: string;
  captcha_code: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string | null;
  captcha_id: string;
  captcha_code: string;
}
