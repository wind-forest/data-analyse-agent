import { Component, type ReactNode } from "react";
import { BarChart3, Table2 } from "lucide-react";
import type { Artifact } from "../../types/api";
import { ChartBlock } from "./ChartBlock";
import { DataTableBlock } from "./DataTableBlock";
import { ModelBlock } from "./ModelBlock";
import { chartNote } from "../../utils/chart";

class ArtifactBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">此产物暂时无法展示，不影响其他分析内容。</div> : this.props.children; }
}

export function ArtifactView({ artifact, compact = false }: { artifact: Artifact; compact?: boolean }) {
  const payload = artifact.payload_json || {};
  const title = artifact.type === "chart" ? "图表" : artifact.type === "model" ? "模型指标" : "数据表";
  return <section id={`artifact-${artifact.id}`} className="my-3 rounded-xl border border-neutral-200 bg-white p-3 dark:border-neutral-800 dark:bg-neutral-950">
    <div className="mb-2 flex items-center gap-2 text-xs font-medium text-neutral-500">{artifact.type === "chart" ? <BarChart3 className="h-4 w-4" /> : <Table2 className="h-4 w-4" />}{title}<span className="ml-auto font-mono text-[10px]">{artifact.id.slice(0, 8)}</span></div>
    <ArtifactBoundary>
      {artifact.type === "chart" && <ChartBlock payload={payload} />}
      {artifact.type === "table" && <DataTableBlock payload={payload} />}
      {artifact.type === "model" && <ModelBlock payload={payload} />}
    </ArtifactBoundary>
    {!compact && artifact.type === "chart" && chartNote(payload) && <p className="mt-2 text-xs text-neutral-500">{chartNote(payload)}</p>}
  </section>;
}
