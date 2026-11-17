import { create } from "zustand";
import type { AnalysisEvent, ApprovalRequiredEvent } from "../types/events";
import { applyEvent, createRun, type RunState } from "./runReducer";

type Theme = "light" | "dark";

function storedValue(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

interface ChatState {
  currentSessionId: string | null;
  selectedFileIds: string[];
  draft: string;
  model: string | null;
  allowCustomCode: boolean;
  run: RunState | null;
  sidebarOpen: boolean;
  artifactsOpen: boolean;
  theme: Theme;
  setCurrentSession: (id: string | null) => void;
  setSelectedFiles: (ids: string[]) => void;
  toggleFile: (id: string) => void;
  setDraft: (draft: string) => void;
  setModel: (model: string) => void;
  setAllowCustomCode: (enabled: boolean) => void;
  startRun: (sessionId: string, messageId: string) => void;
  dispatchEvent: (event: AnalysisEvent) => void;
  setRetryCount: (count: number) => void;
  setConnectionError: (message: string) => void;
  setApproval: (approval: ApprovalRequiredEvent | null) => void;
  clearRun: () => void;
  setSidebarOpen: (open: boolean) => void;
  setArtifactsOpen: (open: boolean) => void;
  toggleTheme: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  currentSessionId: storedValue("analysis-current-session"),
  selectedFileIds: [],
  draft: "",
  model: null,
  allowCustomCode: false,
  run: null,
  sidebarOpen: false,
  artifactsOpen: false,
  theme: storedValue("analysis-theme") === "dark" ? "dark" : "light",
  setCurrentSession: (id) => {
    try {
      if (id) localStorage.setItem("analysis-current-session", id);
      else localStorage.removeItem("analysis-current-session");
    } catch {
      // 本地存储不可用时仍保持当前标签页状态。
    }
    set({ currentSessionId: id, selectedFileIds: [], run: null, artifactsOpen: false, sidebarOpen: false });
  },
  setSelectedFiles: (ids) => set({ selectedFileIds: ids }),
  toggleFile: (id) =>
    set((state) => ({
      selectedFileIds: state.selectedFileIds.includes(id)
        ? state.selectedFileIds.filter((item) => item !== id)
        : [...state.selectedFileIds, id],
    })),
  setDraft: (draft) => set({ draft }),
  setModel: (model) => set({ model }),
  setAllowCustomCode: (allowCustomCode) => set({ allowCustomCode }),
  startRun: (sessionId, messageId) =>
    set((state) => ({
      run: state.run?.messageId === messageId && !state.run.terminal ? state.run : createRun(sessionId, messageId),
    })),
  dispatchEvent: (event) =>
    set((state) => ({
      run: state.run?.messageId === event.message_id ? applyEvent(state.run, event) : state.run,
    })),
  setRetryCount: (retryCount) =>
    set((state) => ({ run: state.run ? { ...state.run, retryCount } : null })),
  setConnectionError: (message) =>
    set((state) => ({
      run: state.run ? { ...state.run, stage: "error", terminal: true, error: message } : null,
    })),
  setApproval: (approval) =>
    set((state) => ({ run: state.run ? { ...state.run, approval } : null })),
  clearRun: () => set({ run: null }),
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  setArtifactsOpen: (artifactsOpen) => set({ artifactsOpen }),
  toggleTheme: () =>
    set((state) => {
      const theme = state.theme === "light" ? "dark" : "light";
      try {
        localStorage.setItem("analysis-theme", theme);
      } catch {
        // 主题仍在当前页面生效。
      }
      return { theme };
    }),
}));
