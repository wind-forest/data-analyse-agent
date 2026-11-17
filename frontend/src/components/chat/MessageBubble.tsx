import { Bot, Loader2 } from "lucide-react";
import type { Artifact, Message } from "../../types/api";
import { toolsFromHistory, visibleTools, type RunState, type ToolCardState } from "../../store/runReducer";
import { Markdown } from "./Markdown";
import { ToolCallCard } from "./ToolCallCard";
import { ArtifactView } from "../artifacts/ArtifactView";
import { stageLabel } from "../../utils/format";

export function assistantView(message: Message, run: RunState | null): { content: string; tools: ToolCardState[] } {
  const activeRun = run?.messageId === message.id ? run : null;
  const useHistory = !activeRun || activeRun.needsHistory || (activeRun.terminal && Boolean(message.content));
  return {
    content: activeRun && !useHistory ? activeRun.content : message.content,
    tools: activeRun && !activeRun.needsHistory && (!activeRun.terminal || !message.tool_calls_json?.length)
      ? visibleTools(activeRun)
      : toolsFromHistory(message.tool_calls_json),
  };
}

interface MessageBubbleProps {
  message: Message;
  run: RunState | null;
  artifacts: Artifact[];
}

export function MessageBubble({ message, run, artifacts }: MessageBubbleProps) {
  if (message.role === "user") {
    return <article id={`message-${message.id}`} className="flex justify-end py-3"><div className="max-w-[88%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-neutral-100 px-4 py-3 text-[15px] leading-7 dark:bg-neutral-800 sm:max-w-[80%]">{message.content}</div></article>;
  }
  const view = assistantView(message, run);
  const current = run?.messageId === message.id ? run : null;
  return <article id={`message-${message.id}`} className="flex gap-3 py-5">
    <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-neutral-200 bg-white dark:border-neutral-700 dark:bg-neutral-900"><Bot className="h-4 w-4 text-blue-600" /></div>
    <div className="min-w-0 flex-1">
      {current && !current.terminal && <div className="mb-3 flex items-center gap-2 text-xs text-neutral-500"><Loader2 className="h-3.5 w-3.5 animate-spin" />{stageLabel(current.stage)}{current.retryCount > 0 && `，第 ${current.retryCount} 次重连`}</div>}
      {view.tools.map((tool) => <ToolCallCard key={tool.callId} tool={tool} />)}
      {view.content ? <Markdown content={view.content} /> : current?.terminal && current.error ? <p className="text-sm text-red-600">{current.error}</p> : !current ? <div className="h-5 w-32 animate-pulse rounded bg-neutral-100 dark:bg-neutral-800" /> : null}
      {artifacts.map((artifact) => <ArtifactView key={artifact.id} artifact={artifact} />)}
    </div>
  </article>;
}
