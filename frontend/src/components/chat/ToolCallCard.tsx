import { Check, ChevronDown, CircleAlert, Loader2, Wrench } from "lucide-react";
import type { ToolCardState } from "../../store/runReducer";
import { toolLabel } from "../../utils/format";

export function ToolCallCard({ tool }: { tool: ToolCardState }) {
  return (
    <details className="group my-3 overflow-hidden rounded-xl border border-neutral-200 bg-neutral-50/70 text-sm dark:border-neutral-800 dark:bg-neutral-900/70">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2.5 [&::-webkit-details-marker]:hidden">
        <Wrench className="h-4 w-4 shrink-0 text-neutral-500" />
        <span className="font-medium">{toolLabel(tool.tool)}</span>
        <span className="flex items-center gap-1 text-xs text-neutral-500">
          {tool.status === "running" && <><Loader2 className="h-3.5 w-3.5 animate-spin" />执行中</>}
          {tool.status === "success" && <><Check className="h-3.5 w-3.5 text-green-600" />已完成</>}
          {tool.status === "failed" && <><CircleAlert className="h-3.5 w-3.5 text-red-600" />执行失败</>}
          {tool.durationMs !== undefined && <span>· {tool.durationMs < 1000 ? `${Math.round(tool.durationMs)} ms` : `${(tool.durationMs / 1000).toFixed(1)} s`}</span>}
        </span>
        <ChevronDown className="ml-auto h-4 w-4 text-neutral-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-3 border-t border-neutral-200 px-3 py-3 dark:border-neutral-800">
        <div><div className="mb-1 text-xs font-medium text-neutral-500">调用参数</div><pre className="max-h-52 overflow-auto rounded-lg bg-white p-2 text-xs dark:bg-neutral-950">{JSON.stringify(tool.params, null, 2)}</pre></div>
        {tool.summary && <div><div className="mb-1 text-xs font-medium text-neutral-500">结果摘要</div><p className="whitespace-pre-wrap text-xs leading-5 text-neutral-700 dark:text-neutral-300">{tool.summary}</p></div>}
        {tool.error && <p className="text-xs text-red-600">{tool.error}</p>}
      </div>
    </details>
  );
}
