import { useEffect, useRef, useState } from "react";
import { ArrowDown, Database, LineChart, TableProperties } from "lucide-react";
import type { Artifact, Message } from "../../types/api";
import type { RunState } from "../../store/runReducer";
import { useChatStore } from "../../store/chatStore";
import { MessageBubble, assistantView } from "./MessageBubble";
import { Button } from "../ui/button";

export function artifactsForMessage(message: Message, run: RunState | null, artifacts: Artifact[]): Artifact[] {
  const toolIds = assistantView(message, run).tools.flatMap((tool) => tool.artifactIds);
  const matched = artifacts.filter((artifact) => artifact.message_id === message.id || toolIds.includes(artifact.id));
  if (run?.messageId !== message.id) return matched;
  const existing = new Set(matched.map((item) => item.id));
  const streamed = run.artifacts.filter((item) => !existing.has(item.id)).map((item) => ({
    id: item.id,
    run_id: "",
    message_id: message.id,
    type: item.type,
    payload_json: item.payload,
    file_path: null,
    created_at: message.created_at,
  }));
  return [...matched, ...streamed];
}

interface MessageListProps {
  messages: Message[];
  artifacts: Artifact[];
  loading: boolean;
}

export function MessageList({ messages, artifacts, loading }: MessageListProps) {
  const run = useChatStore((state) => state.run);
  const setDraft = useChatStore((state) => state.setDraft);
  const scrollRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const [showNew, setShowNew] = useState(false);
  const scrollToBottom = () => {
    const element = scrollRef.current;
    if (element) element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
    atBottom.current = true;
    setShowNew(false);
  };
  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    if (atBottom.current) element.scrollTop = element.scrollHeight;
    else setShowNew(true);
  }, [messages, run?.content, run?.toolOrder.length]);

  return <div className="relative min-h-0 flex-1">
    <div ref={scrollRef} onScroll={(event) => {
      const element = event.currentTarget;
      atBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 100;
      if (atBottom.current) setShowNew(false);
    }} className="h-full overflow-y-auto px-4 md:px-6">
      <div className="mx-auto w-full max-w-3xl pb-8">
        {loading && <div className="space-y-4 py-8"><div className="h-16 animate-pulse rounded-xl bg-neutral-100 dark:bg-neutral-800" /><div className="h-28 animate-pulse rounded-xl bg-neutral-100 dark:bg-neutral-800" /></div>}
        {!loading && !messages.length && <div className="flex min-h-full flex-col items-center justify-center py-16 text-center"><h2 className="text-2xl font-semibold tracking-tight">今天想分析什么？</h2><p className="mt-3 max-w-md text-sm leading-6 text-neutral-500">上传数据文件后，可以探索数据质量、汇总指标、分析趋势或训练预测模型。</p><div className="mt-8 grid w-full gap-3 sm:grid-cols-3">{[
          { icon: Database, text: "检查数据概况和缺失情况" },
          { icon: TableProperties, text: "按维度汇总核心指标" },
          { icon: LineChart, text: "分析时间趋势并生成图表" },
        ].map(({ icon: Icon, text }) => <button key={text} className="rounded-xl border border-neutral-200 p-4 text-left text-sm hover:border-blue-300 hover:bg-blue-50/50 dark:border-neutral-800 dark:hover:bg-blue-950/30" onClick={() => setDraft(text)}><Icon className="mb-3 h-5 w-5 text-blue-600" />{text}</button>)}</div></div>}
        {messages.map((message) => <MessageBubble key={message.id} message={message} run={run?.messageId === message.id ? run : null} artifacts={artifactsForMessage(message, run?.messageId === message.id ? run : null, artifacts)} />)}
      </div>
    </div>
    {showNew && <Button size="sm" className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full shadow-lg" onClick={scrollToBottom}><ArrowDown className="h-4 w-4" />查看新消息</Button>}
  </div>;
}
