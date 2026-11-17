import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function toolLabel(name: string): string {
  const labels: Record<string, string> = {
    profile_dataset: "读取数据概况",
    aggregate_plays: "聚合数据",
    build_time_features: "构建时间特征",
    train_predictive_model: "训练预测模型",
    evaluate_model: "评估模型",
    generate_chart_data: "生成图表",
    query_session_memory: "查询会话记忆",
    execute_python_snippet: "执行自定义代码",
    finish: "整理结论",
  };
  return labels[name] || name;
}

export function stageLabel(stage: string): string {
  const labels: Record<string, string> = {
    queued: "等待分析",
    thinking: "正在思考",
    tool_running: "正在调用工具",
    approval: "等待审批",
    finishing: "正在整理结论",
    done: "分析完成",
    restoring: "正在恢复历史",
    error: "连接中断",
  };
  return labels[stage] || "正在分析";
}
