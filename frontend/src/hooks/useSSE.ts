import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ANALYSIS_EVENT_NAMES, type AnalysisEvent } from "../types/events";
import { queryKeys } from "../queries";
import { useChatStore } from "../store/chatStore";

export function useSSE(sessionId: string | null) {
  const queryClient = useQueryClient();
  const messageId = useChatStore((state) =>
    state.run?.sessionId === sessionId ? state.run.messageId : null,
  );
  const terminal = useChatStore((state) =>
    state.run?.sessionId === sessionId ? state.run.terminal : true,
  );
  const sourceRef = useRef<EventSource | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!sessionId || !messageId || terminal) return;
    let disposed = false;

    const close = () => {
      sourceRef.current?.close();
      sourceRef.current = null;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
    };

    const invalidateTerminal = () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.messages(sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.artifacts(sessionId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
    };

    const connect = () => {
      if (disposed) return;
      const state = useChatStore.getState().run;
      if (!state || state.messageId !== messageId || state.terminal) return;
      const lastEventId = state.lastEventId;
      const source = new EventSource(
        `/api/sessions/${sessionId}/stream?message_id=${messageId}&last_event_id=${lastEventId}`,
      );
      sourceRef.current = source;
      source.onopen = () => useChatStore.getState().setRetryCount(0);

      const listeners = ANALYSIS_EVENT_NAMES.map((name) => {
        const listener = (raw: Event) => {
          const event = JSON.parse((raw as MessageEvent).data) as AnalysisEvent;
          const current = useChatStore.getState().run;
          if (!current || current.messageId !== event.message_id) return;
          useChatStore.getState().dispatchEvent(event);
          if (event.event === "artifact") {
            void queryClient.invalidateQueries({ queryKey: queryKeys.artifacts(sessionId) });
          }
          if (event.event === "done" || event.event === "error") {
            invalidateTerminal();
            close();
          }
        };
        source.addEventListener(name, listener);
        return { name, listener };
      });

      source.onerror = () => {
        source.close();
        listeners.forEach(({ name, listener }) => source.removeEventListener(name, listener));
        if (sourceRef.current === source) sourceRef.current = null;
        if (disposed) return;
        const current = useChatStore.getState().run;
        if (!current || current.messageId !== messageId || current.terminal) return;
        if (current.retryCount >= 3) {
          useChatStore.getState().setConnectionError("连接已中断，请切换会话后重试恢复。 ");
          return;
        }
        const nextRetry = current.retryCount + 1;
        useChatStore.getState().setRetryCount(nextRetry);
        timerRef.current = window.setTimeout(connect, 1000 * 2 ** (nextRetry - 1));
      };
    };

    connect();
    return () => {
      disposed = true;
      close();
    };
  }, [sessionId, messageId, terminal, queryClient]);
}
