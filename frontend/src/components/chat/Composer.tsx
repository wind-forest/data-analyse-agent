import { useEffect, useRef } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import type { AppConfig, DataFile } from "../../types/api";
import { useChatStore } from "../../store/chatStore";
import { Button } from "../ui/button";

interface ComposerProps {
  sessionId: string | null;
  files: DataFile[];
  config?: AppConfig;
  sending: boolean;
  error: string | null;
  onSend: (content: string) => void;
}

export function Composer({ sessionId, files, config, sending, error, onSend }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);
  const draft = useChatStore((state) => state.draft);
  const setDraft = useChatStore((state) => state.setDraft);
  const allowCustomCode = useChatStore((state) => state.allowCustomCode);
  const setAllowCustomCode = useChatStore((state) => state.setAllowCustomCode);
  const running = useChatStore((state) => Boolean(state.run && state.run.sessionId === sessionId && !state.run.terminal));
  const hasReadyFiles = files.some((file) => file.status === "ready");
  const disabled = !sessionId || !draft.trim() || !hasReadyFiles || sending || running;

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 180)}px`;
  }, [draft]);

  const submit = () => {
    if (!disabled) onSend(draft.trim());
  };

  return (
    <div className="mx-auto w-full max-w-3xl">
      <div className="rounded-2xl border border-neutral-300 bg-white p-2 shadow-sm focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 dark:border-neutral-700 dark:bg-neutral-900 dark:focus-within:ring-blue-950">
        <textarea
          ref={textareaRef}
          rows={1}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onCompositionStart={() => { composing.current = true; }}
          onCompositionEnd={() => { composing.current = false; }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !composing.current && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
          placeholder={sessionId ? hasReadyFiles ? "输入你的数据分析问题，Enter 发送" : "请先上传并等待数据文件就绪" : "请先新建分析会话"}
          aria-label="分析问题的数据"
          className="max-h-44 min-h-11 w-full resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 outline-none placeholder:text-neutral-400"
        />
        <div className="flex items-center justify-between gap-2 px-1 pb-0.5">
          <label className="flex cursor-pointer items-center gap-2 px-2 text-xs text-neutral-500">
            <input type="checkbox" className="h-3.5 w-3.5 rounded" checked={allowCustomCode} disabled={!config?.custom_code_available || running} onChange={(event) => setAllowCustomCode(event.target.checked)} />
            自定义代码{config && !config.custom_code_available ? "（沙箱不可用）" : "（执行前需审批）"}
          </label>
          <Button size="icon" className="h-9 w-9 rounded-full" disabled={disabled} onClick={submit} aria-label="发送问题">{sending || running ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-5 w-5" />}</Button>
        </div>
      </div>
      {error && <p role="alert" className="mt-2 px-2 text-sm text-red-600">{error}</p>}
      <p className="mt-2 text-center text-xs text-neutral-400">分析结果由模型生成，请结合原始数据核对。</p>
    </div>
  );
}
