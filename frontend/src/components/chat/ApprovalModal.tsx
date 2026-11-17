import { ShieldAlert } from "lucide-react";
import type { ApprovalRequiredEvent } from "../../types/events";
import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "../ui/dialog";
import { toolLabel } from "../../utils/format";

interface ApprovalModalProps {
  approval: ApprovalRequiredEvent;
  pending: boolean;
  error: string | null;
  onDecision: (decision: "approved" | "rejected") => void;
}

export function ApprovalModal({ approval, pending, error, onDecision }: ApprovalModalProps) {
  return (
    <Dialog open onOpenChange={() => undefined}>
      <DialogContent showClose={false} onEscapeKeyDown={(event) => event.preventDefault()} onPointerDownOutside={(event) => event.preventDefault()}>
        <div className="flex items-start gap-3"><span className="rounded-full bg-amber-100 p-2 text-amber-700 dark:bg-amber-950"><ShieldAlert className="h-5 w-5" /></span><div><DialogTitle className="text-lg font-semibold">需要批准高风险操作</DialogTitle><DialogDescription className="mt-1 text-sm text-neutral-500">请检查工具和参数。只有批准后，自定义代码才会在隔离沙箱中执行。</DialogDescription></div></div>
        <div className="mt-5 rounded-xl border border-neutral-200 bg-neutral-50 p-3 dark:border-neutral-800 dark:bg-neutral-950"><div className="mb-2 text-sm font-medium">{toolLabel(approval.tool)}</div><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs leading-5">{JSON.stringify(approval.params, null, 2)}</pre></div>
        {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
        <div className="mt-6 flex justify-end gap-2"><Button variant="outline" disabled={pending} onClick={() => onDecision("rejected")}>拒绝执行</Button><Button disabled={pending} onClick={() => onDecision("approved")}>{pending ? "正在提交…" : "批准并继续"}</Button></div>
      </DialogContent>
    </Dialog>
  );
}
