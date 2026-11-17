import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { chartOption } from "../../utils/chart";
import { useChatStore } from "../../store/chatStore";

export function ChartBlock({ payload }: { payload: Record<string, unknown> }) {
  const elementRef = useRef<HTMLDivElement>(null);
  const theme = useChatStore((state) => state.theme);
  useEffect(() => {
    if (!elementRef.current) return;
    const instance = echarts.init(elementRef.current, theme === "dark" ? "dark" : undefined, { renderer: "canvas" });
    instance.setOption(chartOption(payload, theme === "dark"), true);
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(elementRef.current);
    return () => {
      observer.disconnect();
      instance.dispose();
    };
  }, [payload, theme]);
  return <div ref={elementRef} className="h-72 w-full" role="img" aria-label="分析图表" />;
}
