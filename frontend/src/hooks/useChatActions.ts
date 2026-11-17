import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/endpoints";
import { queryKeys } from "../queries";
import { useChatStore } from "../store/chatStore";

export function useChatActions(sessionId: string | null) {
  const queryClient = useQueryClient();
  const startRun = useChatStore((state) => state.startRun);
  const setApproval = useChatStore((state) => state.setApproval);
  const setDraft = useChatStore((state) => state.setDraft);

  const send = useMutation({
    mutationFn: async (content: string) => {
      const state = useChatStore.getState();
      if (!sessionId) throw new Error("请先新建分析会话");
      return api.sendMessage(sessionId, {
        content,
        file_ids: state.selectedFileIds,
        model: state.model || undefined,
        allow_custom_code: state.allowCustomCode,
      });
    },
    onSuccess: ({ message_id }) => {
      if (!sessionId) return;
      setDraft("");
      startRun(sessionId, message_id);
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
  });

  const create = useMutation({
    mutationFn: () => api.createSession(),
    onSuccess: (session) => {
      useChatStore.getState().setCurrentSession(session.id);
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteSession(id),
    onSuccess: (_, id) => {
      if (useChatStore.getState().currentSessionId === id) {
        useChatStore.getState().setCurrentSession(null);
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    },
  });

  const approval = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approved" | "rejected" }) =>
      api.decideApproval(id, decision),
    onSuccess: () => setApproval(null),
  });

  return { send, create, remove, approval };
}
