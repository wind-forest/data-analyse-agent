function display(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function DataTableBlock({ payload }: { payload: Record<string, unknown> }) {
  const candidate = payload.rows ?? payload.sample_rows ?? payload.forecast;
  const rows = Array.isArray(candidate) ? candidate.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row)) : [];
  if (!rows.length) return <div className="rounded-lg bg-neutral-50 p-4 text-sm text-neutral-500 dark:bg-neutral-900">该表格产物没有可展示的行数据。</div>;
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const visible = rows.slice(0, 100);
  return <div>
    <div className="max-h-96 overflow-auto rounded-lg border border-neutral-200 dark:border-neutral-800"><table className="w-full border-collapse text-left text-xs"><thead className="sticky top-0 bg-neutral-100 dark:bg-neutral-800"><tr>{columns.map((column) => <th key={column} className="whitespace-nowrap border-b border-neutral-200 px-3 py-2 font-medium dark:border-neutral-700">{column}</th>)}</tr></thead><tbody>{visible.map((row, index) => <tr key={index} className="odd:bg-white even:bg-neutral-50 dark:odd:bg-neutral-900 dark:even:bg-neutral-950">{columns.map((column) => <td key={column} className="max-w-64 truncate border-b border-neutral-100 px-3 py-2 dark:border-neutral-800" title={display(row[column])}>{display(row[column])}</td>)}</tr>)}</tbody></table></div>
    {rows.length > 100 && <p className="mt-2 text-xs text-neutral-500">共 {rows.length} 行，仅展示前 100 行。</p>}
  </div>;
}
