import { request } from "./client";
import type {
  AppConfig,
  Artifact,
  CaptchaResponse,
  DataFile,
  LoginRequest,
  MeResponse,
  Message,
  MessagePayload,
  RegisterRequest,
  Session,
  User,
} from "../types/api";

export const api = {
  config: () => request<AppConfig>("/config"),
  sessions: () => request<Session[]>("/sessions"),
  createSession: (title = "新分析") =>
    request<Session>("/sessions", { method: "POST", body: JSON.stringify({ title }) }),
  deleteSession: (id: string) => request<void>(`/sessions/${id}`, { method: "DELETE" }),
  messages: (sessionId: string) => request<Message[]>(`/sessions/${sessionId}/messages`),
  sendMessage: (sessionId: string, payload: MessagePayload) =>
    request<{ message_id: string }>(`/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  files: (sessionId: string) => request<DataFile[]>(`/files?session_id=${sessionId}`),
  deleteFile: (sessionId: string, fileId: string) =>
    request<void>(`/files/${fileId}?session_id=${sessionId}`, { method: "DELETE" }),
  artifacts: (sessionId: string) => request<Artifact[]>(`/sessions/${sessionId}/artifacts`),
  decideApproval: (approvalId: string, decision: "approved" | "rejected") =>
    request<{ approval_id: string; status: string; message_id: string }>(`/approvals/${approvalId}`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    }),
  // Auth
  captcha: () => request<CaptchaResponse>("/auth/captcha"),
  register: (payload: RegisterRequest) =>
    request<User>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload: LoginRequest) =>
    request<{ user: User }>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<MeResponse>("/auth/me"),
  updateProfile: (payload: { display_name: string | null }) =>
    request<User>("/auth/me", { method: "PATCH", body: JSON.stringify(payload) }),
  changePassword: (payload: { old_password: string; new_password: string }) =>
    request<{ status: string }>("/auth/change-password", { method: "POST", body: JSON.stringify(payload) }),
  deleteAccount: () => request<void>("/auth/me", { method: "DELETE" }),
};
