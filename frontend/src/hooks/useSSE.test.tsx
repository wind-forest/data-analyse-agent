import { StrictMode, type ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSSE } from "./useSSE";
import { useChatStore } from "../store/chatStore";
import type { AnalysisEventName } from "../types/events";

class MockEventSource {
  static instances: MockEventSource[] = [];
  listeners = new Map<string, Set<(event: Event) => void>>();
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) { MockEventSource.instances.push(this); }
  addEventListener(name: string, listener: (event: Event) => void) {
    const listeners = this.listeners.get(name) || new Set();
    listeners.add(listener);
    this.listeners.set(name, listeners);
  }
  removeEventListener(name: string, listener: (event: Event) => void) { this.listeners.get(name)?.delete(listener); }
  close() { this.closed = true; }
  emit(name: AnalysisEventName, body: Record<string, unknown>) {
    const event = { data: JSON.stringify(body) } as MessageEvent;
    this.listeners.get(name)?.forEach((listener) => listener(event));
  }
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <StrictMode><QueryClientProvider client={client}>{children}</QueryClientProvider></StrictMode>;
}

describe("useSSE", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    useChatStore.setState({ run: null, currentSessionId: "s1" });
  });
  afterEach(() => {
    useChatStore.getState().clearRun();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("按 last_event_id 重连、去重并在卸载时清理", () => {
    useChatStore.getState().startRun("s1", "m1");
    const { unmount } = renderHook(() => useSSE("s1"), { wrapper });
    const first = MockEventSource.instances.at(-1)!;
    expect(first.url).toContain("last_event_id=0");
    const token = { event_id: 1, message_id: "m1", timestamp: "now", event: "token", delta: "结果" };
    act(() => first.emit("token", token));
    expect(useChatStore.getState().run?.content).toBe("结果");
    act(() => first.onerror?.());
    expect(first.closed).toBe(true);
    act(() => { vi.advanceTimersByTime(1000); });
    const second = MockEventSource.instances.at(-1)!;
    expect(second).not.toBe(first);
    expect(second.url).toContain("last_event_id=1");
    act(() => {
      second.emit("token", token);
      second.emit("token", { ...token, event_id: 2, delta: "完成" });
    });
    expect(useChatStore.getState().run?.content).toBe("结果完成");
    unmount();
    expect(second.closed).toBe(true);
  });

  it("指数退避最多三次，收到 done 后停止", () => {
    useChatStore.getState().startRun("s1", "m1");
    const { unmount } = renderHook(() => useSSE("s1"), { wrapper });
    for (const delay of [1000, 2000, 4000]) {
      const source = MockEventSource.instances.at(-1)!;
      act(() => source.onerror?.());
      act(() => { vi.advanceTimersByTime(delay); });
    }
    const last = MockEventSource.instances.at(-1)!;
    act(() => last.onerror?.());
    expect(useChatStore.getState().run?.terminal).toBe(true);
    const count = MockEventSource.instances.length;
    act(() => { vi.advanceTimersByTime(10000); });
    expect(MockEventSource.instances.length).toBe(count);
    unmount();
  });

  it("EVENT_GAP 后不再重连并等待历史快照", () => {
    useChatStore.getState().startRun("s1", "m1");
    renderHook(() => useSSE("s1"), { wrapper });
    const source = MockEventSource.instances.at(-1)!;
    act(() => source.emit("error", { event_id: 1, message_id: "m1", timestamp: "now", event: "error", code: "EVENT_GAP", message: "过期", retryable: false }));
    expect(useChatStore.getState().run?.needsHistory).toBe(true);
    const count = MockEventSource.instances.length;
    act(() => { vi.advanceTimersByTime(10000); });
    expect(MockEventSource.instances.length).toBe(count);
  });
});
