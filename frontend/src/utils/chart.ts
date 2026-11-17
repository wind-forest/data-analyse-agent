import type { EChartsOption } from "echarts";

interface ChartSeries { name?: string; data?: unknown[] }
interface ChartPayload {
  chart_type?: string;
  data?: { x?: unknown[]; series?: ChartSeries[] };
  meta?: Record<string, unknown>;
}

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function chartOption(payload: Record<string, unknown>, dark = false): EChartsOption {
  const chart = payload as unknown as ChartPayload;
  const data = chart.data || {};
  const labels = (data.x || []).map((value) => String(value ?? ""));
  const series = (data.series || []).filter((item) => Array.isArray(item.data));
  const type = chart.chart_type === "line" || chart.chart_type === "scatter" ? chart.chart_type : "bar";
  let order = labels.map((_, index) => index);
  if (type === "line" && labels.length && labels.every((label) => Number.isFinite(Date.parse(label)))) {
    order = order.sort((a, b) => Date.parse(labels[a]) - Date.parse(labels[b]));
  }
  const x = order.map((index) => labels[index]);
  const meta = chart.meta || {};
  const foreground = dark ? "#d4d4d4" : "#525252";
  return {
    animation: false,
    backgroundColor: "transparent",
    title: meta.title ? { text: String(meta.title), textStyle: { color: foreground, fontSize: 14 } } : undefined,
    tooltip: { trigger: type === "scatter" ? "item" : "axis" },
    legend: series.length > 1 ? { top: 4, textStyle: { color: foreground } } : undefined,
    grid: { left: 52, right: 20, top: series.length > 1 ? 44 : 28, bottom: 52 },
    xAxis: { type: "category", data: x, name: String(payload.x || ""), axisLabel: { color: foreground, rotate: x.length > 10 ? 30 : 0 }, axisLine: { lineStyle: { color: foreground } } },
    yAxis: { type: "value", name: String(meta.unit || payload.y || ""), axisLabel: { color: foreground }, splitLine: { lineStyle: { color: dark ? "#333" : "#eee" } } },
    series: series.map((item) => ({
      name: String(item.name || payload.y || "数值"),
      type,
      data: order.map((index) => finiteNumber(item.data?.[index])),
      smooth: type === "line",
      showSymbol: type === "scatter" || x.length < 40,
      itemStyle: { color: type === "bar" ? "#4f7cff" : undefined },
    })),
  };
}

export function chartNote(payload: Record<string, unknown>): string | null {
  const meta = (payload.meta || {}) as Record<string, unknown>;
  const notes: string[] = [];
  if (meta.truncated) notes.push(`数据已抽样，展示前 ${Number(meta.points) || 5000} 个数据点`);
  if (meta.sample_note) notes.push(String(meta.sample_note));
  return notes.join("；") || null;
}
