import { Dialog } from "@radix-ui/react-dialog";
import type { Artifact } from "../../types/api";
import { useChatStore } from "../../store/chatStore";
import { DialogContent, DialogDescription, DialogTitle } from "../ui/dialog";
import { ArtifactView } from "./ArtifactView";
import { Button } from "../ui/button";

export function ArtifactDrawer({ artifacts }: { artifacts: Artifact[] }) {
  const open = useChatStore((state) => state.artifactsOpen);
  const setOpen = useChatStore((state) => state.setArtifactsOpen);
  const locate = (artifact: Artifact) => {
    if (!artifact.message_id) return;
    setOpen(false);
    window.setTimeout(() => document.getElementById(`message-${artifact.message_id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
  };
  return <Dialog open={open} onOpenChange={setOpen}><DialogContent className="left-auto right-0 top-0 h-full max-h-none w-full max-w-2xl translate-x-0 translate-y-0 rounded-none border-y-0 border-r-0 p-4 sm:p-6" aria-describedby="artifact-description">
    <DialogTitle className="pr-8 text-lg font-semibold">分析产物</DialogTitle><DialogDescription id="artifact-description" className="mt-1 text-sm text-neutral-500">查看图表、数据表和模型指标，或定位到生成它们的消息。</DialogDescription>
    <div className="mt-5 space-y-3">{artifacts.map((artifact) => <div key={artifact.id}><ArtifactView artifact={artifact} compact />{artifact.message_id && <Button variant="ghost" size="sm" onClick={() => locate(artifact)}>定位到原消息</Button>}</div>)}{!artifacts.length && <div className="py-16 text-center text-sm text-neutral-500">完成分析后，图表和模型产物会显示在这里。</div>}</div>
  </DialogContent></Dialog>;
}
