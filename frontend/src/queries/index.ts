import { useQuery } from "@tanstack/react-query";
import { api } from "../api/endpoints";

export const queryKeys = {
  config: ["config"] as const,
  sessions: ["sessions"] as const,
  messages: (id: string) => ["sessions", id, "messages"] as const,
  files: (id: string) => ["sessions", id, "files"] as const,
  artifacts: (id: string) => ["sessions", id, "artifacts"] as const,
};

export function useConfig() {
  return useQuery({ queryKey: queryKeys.config, queryFn: api.config, staleTime: Infinity });
}

export function useSessions() {
  return useQuery({ queryKey: queryKeys.sessions, queryFn: api.sessions });
}

export function useMessages(sessionId: string | null) {
  return useQuery({
    queryKey: queryKeys.messages(sessionId || "none"),
    queryFn: () => api.messages(sessionId!),
    enabled: Boolean(sessionId),
  });
}

export function useFiles(sessionId: string | null) {
  return useQuery({
    queryKey: queryKeys.files(sessionId || "none"),
    queryFn: () => api.files(sessionId!),
    enabled: Boolean(sessionId),
  });
}

export function useArtifacts(sessionId: string | null) {
  return useQuery({
    queryKey: queryKeys.artifacts(sessionId || "none"),
    queryFn: () => api.artifacts(sessionId!),
    enabled: Boolean(sessionId),
  });
}

// --- Auth ---

export const authQueryKeys = {
  me: ["auth", "me"] as const,
};

export function useMe() {
  return useQuery({
    queryKey: authQueryKeys.me,
    queryFn: api.me,
    staleTime: 30_000,
  });
}

export function useCaptcha() {
  return useQuery({
    queryKey: ["auth", "captcha", Math.random().toString(36).slice(2)],
    queryFn: api.captcha,
    staleTime: 0,
  });
}
