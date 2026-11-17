import { useEffect, useRef } from "react";
import { Plus } from "lucide-react";
import { useArtifacts, useConfig, useFiles, useMessages, useSessions } from "../../queries";
import { useChatStore } from "../../store/chatStore";
import { useAuthStore } from "../../store/authStore";
import { useChatActions } from "../../hooks/useChatActions";
import { useSSE } from "../../hooks/useSSE";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { MessageList } from "./MessageList";
import { FileUpload } from "./FileUpload";
import { Composer } from "./Composer";
import { ApprovalModal } from "./ApprovalModal";
import { ArtifactDrawer } from "../artifacts/ArtifactDrawer";
import { Button } from "../ui/button";
import type { ApiError } from "../../api/client";

const ANON_LIMIT_CODES = new Set(["ANON_SESSION_LIMIT", "ANON_MESSAGE_LIMIT"]);

export function ChatPage() {
  const config = useConfig();
  const sessions = useSessions();
  const currentId = useChatStore((state) => state.currentSessionId);
  const setCurrentId = useChatStore((state) => state.setCurrentSession);
  const setModel = useChatStore((state) => state.setModel);
  const setSelectedFiles = useChatStore((state) => state.setSelectedFiles);
  const theme = useChatStore((state) => state.theme);
  const run = useChatStore((state) => state.run);
  const messages = useMessages(currentId);
  const files = useFiles(currentId);
  const artifacts = useArtifacts(currentId);
  const actions = useChatActions(currentId);
  const initializedFiles = useRef<string | null>(null);
  useSSE(currentId);

  const openAuthModal = useAuthStore((state) => state.openAuthModal);

  // 监听限额错误，自动打开登录弹窗
  useEffect(() => {
    const err = (actions.send.error || actions.create.error) as ApiError | null;
    if (err && ANON_LIMIT_CODES.has(err.code)) {
      openAuthModal();
    }
  }, [actions.send.error, actions.create.error, openAuthModal]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  }, [theme]);

  useEffect(() => {
    if (config.data && !useChatStore.getState().model) setModel(config.data.default_model);
  }, [config.data, setModel]);

  useEffect(() => {
    if (!sessions.data || sessions.isFetching) return;
    if (!currentId) setCurrentId(sessions.data[0]?.id || null);
    else if (!sessions.data.some((item) => item.id === currentId)) setCurrentId(sessions.data[0]?.id || null);
  }, [sessions.data, sessions.isFetching, currentId, setCurrentId]);

  useEffect(() => {
    if (!currentId || !messages.data) return;
    const currentRun = useChatStore.getState().run;
    if (currentRun?.sessionId === currentId) return;
    const unfinished = [...messages.data].reverse().find((message) => message.role === "assistant" && message.finish_reason === null);
    if (unfinished) useChatStore.getState().startRun(currentId, unfinished.id);
  }, [currentId, messages.data]);

  useEffect(() => {
    if (!currentId || !files.data || initializedFiles.current === currentId) return;
    initializedFiles.current = currentId;
    setSelectedFiles(files.data.filter((file) => file.status === "ready").map((file) => file.id));
  }, [currentId, files.data, setSelectedFiles]);

  const session = sessions.data?.find((item) => item.id === currentId);
  const currentRun = run?.sessionId === currentId ? run : null;

  return <div className="flex h-dvh overflow-hidden bg-white text-neutral-900 dark:bg-neutral-900 dark:text-neutral-100">
    <Sidebar sessions={sessions.data || []} onCreate={() => actions.create.mutate()} onDelete={(id) => actions.remove.mutate(id)} creating={actions.create.isPending} />
    <main className="flex min-w-0 flex-1 flex-col">
      <Header session={session} config={config.data} fileCount={files.data?.length || 0} artifactCount={artifacts.data?.length || 0} />
      {currentId ? <>
        <MessageList messages={messages.data || []} artifacts={artifacts.data || []} loading={messages.isLoading} />
        <footer className="shrink-0 bg-gradient-to-t from-white via-white to-transparent px-3 pb-3 pt-1 dark:from-neutral-900 dark:via-neutral-900 md:px-6 md:pb-5">
          <div className="mx-auto max-w-3xl"><FileUpload sessionId={currentId} files={files.data || []} config={config.data} /></div>
          <Composer sessionId={currentId} files={files.data || []} config={config.data} sending={actions.send.isPending} error={actions.send.error?.message || null} onSend={(content) => actions.send.mutate(content)} />
        </footer>
      </> : <div className="flex flex-1 items-center justify-center p-6 text-center"><div><h2 className="text-2xl font-semibold">开始一次新的数据分析</h2><p className="mt-3 text-sm text-neutral-500">创建会话后上传 CSV、TSV 或 Excel 数据文件。</p><Button className="mt-6" onClick={() => actions.create.mutate()} disabled={actions.create.isPending}><Plus className="h-4 w-4" />新建分析</Button></div></div>}
      <ArtifactDrawer artifacts={artifacts.data || []} />
      {currentRun?.approval && <ApprovalModal approval={currentRun.approval} pending={actions.approval.isPending} error={actions.approval.error?.message || null} onDecision={(decision) => actions.approval.mutate({ id: currentRun.approval!.approval_id, decision })} />}
    </main>
  </div>;
}
