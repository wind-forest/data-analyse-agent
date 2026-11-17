import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChartBlock } from "./ChartBlock";

const mocks = vi.hoisted(() => ({ dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() }));
vi.mock("echarts", () => ({ init: vi.fn(() => ({ dispose: mocks.dispose, resize: mocks.resize, setOption: mocks.setOption })) }));

describe("ChartBlock", () => {
  it("卸载时断开尺寸监听并销毁 ECharts", () => {
    const { unmount } = render(<ChartBlock payload={{ chart_type: "bar", data: { x: [], series: [] } }} />);
    expect(mocks.setOption).toHaveBeenCalled();
    unmount();
    expect(mocks.dispose).toHaveBeenCalledTimes(1);
  });
});
