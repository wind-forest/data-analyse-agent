import { describe, expect, it } from "vitest";
import { chartNote, chartOption } from "./chart";

describe("chartOption", () => {
  it("时间序列按时间排序，并保留系列对应关系", () => {
    const option = chartOption({ chart_type: "line", x: "date", y: "plays", data: { x: ["2026-01-03", "2026-01-01", "2026-01-02"], series: [{ name: "播放量", data: [30, 10, 20] }] }, meta: { unit: "次" } });
    expect((option.xAxis as { data: string[] }).data).toEqual(["2026-01-01", "2026-01-02", "2026-01-03"]);
    expect((option.series as Array<{ data: number[] }>)[0].data).toEqual([10, 20, 30]);
    expect((option.yAxis as { name: string }).name).toBe("次");
  });

  it("柱状 Top N 保持后端顺序，异常值转为空值", () => {
    const option = chartOption({ chart_type: "bar", data: { x: ["B", "A"], series: [{ data: [2, "bad"] }] }, meta: {} });
    expect((option.xAxis as { data: string[] }).data).toEqual(["B", "A"]);
    expect((option.series as Array<{ data: Array<number | null> }>)[0].data).toEqual([2, null]);
  });

  it("读取抽样说明", () => {
    expect(chartNote({ meta: { truncated: true, points: 5000 } })).toContain("抽样");
  });
});
