export function ModelBlock({ payload }: { payload: Record<string, unknown> }) {
  const metrics = (payload.metrics || {}) as Record<string, unknown>;
  const features = Array.isArray(payload.feature_importance) ? payload.feature_importance.slice(0, 8) as Record<string, unknown>[] : [];
  return <div className="space-y-4 text-sm">
    <div><span className="font-medium">{String(payload.model_family || "预测模型")}</span><span className="ml-2 text-xs text-neutral-500">{String(payload.task || "model")} · {String(payload.target || "")}</span></div>
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{Object.entries(metrics).map(([name, value]) => <div key={name} className="rounded-lg bg-neutral-50 p-3 dark:bg-neutral-900"><div className="text-xs uppercase text-neutral-500">{name}</div><div className="mt-1 font-semibold">{typeof value === "number" ? value.toFixed(4) : String(value)}</div></div>)}</div>
    {features.length > 0 && <div><div className="mb-2 text-xs font-medium text-neutral-500">主要特征</div><div className="space-y-2">{features.map((item, index) => {
      const name = String(item.feature ?? item.name ?? `特征 ${index + 1}`);
      const raw = item.importance ?? item.value ?? 0;
      const value = typeof raw === "number" ? raw : Number(raw) || 0;
      return <div key={name} className="flex items-center gap-2 text-xs"><span className="w-28 truncate">{name}</span><div className="h-2 flex-1 rounded-full bg-neutral-100 dark:bg-neutral-800"><div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(100, Math.max(2, value * 100))}%` }} /></div><span>{value.toFixed(3)}</span></div>;
    })}</div></div>}
  </div>;
}
