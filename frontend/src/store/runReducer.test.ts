import { describe, expect, it } from "vitest";
import type { AnalysisEvent } from "../types/events";
import { applyEvent, createRun, toolsFromHistory, visibleTools } from "./runReducer";

const base = { message_id: "m1", timestamp: "2026-01-01T00:00:00Z" };
const event = (event_id: number, values: Record<string, unknown>) => ({ ...base, event_id, ...values }) as AnalysisEvent;

describe("runReducer", () => {
  it("处理完整事件序列并关联工具状态与产物", () => {
    let state = createRun("s1", "m1");
    state = applyEvent(state, event(1, { event: "status", stage: "thinking", iteration: 1 }));
    state = applyEvent(state, event(2, { event: "token", delta: "分析" }));
    state = applyEvent(state, event(3, { event: "tool_call", call_id: "c1", run_id: "r1", tool: "profile_dataset", params: { file_id: "f1" } }));
    expect(visibleTools(state)[0].status).toBe("running");
    state = applyEvent(state, event(4, { event: "tool_result", call_id: "c1", run_id: "r1", status: "success", summary: "共 20 行", artifact_ids: ["a1"], duration_ms: 32, error: null }));
    state = applyEvent(state, event(5, { event: "artifact", artifact_id: "a1", type: "table", payload: { rows: [] } }));
    state = applyEvent(state, event(6, { event: "approval_required", approval_id: "p1", run_id: "r2", tool: "execute_python_snippet", params: { code: "print(1)" }, expires_in_seconds: 600 }));
    state = applyEvent(state, event(7, { event: "status", stage: "thinking", iteration: 2 }));
    expect(state.approval).toBeNull();
    state = applyEvent(state, event(8, { event: "done", finish_reason: "completed" }));
    expect(state.content).toBe("分析");
    expect(visibleTools(state)[0]).toMatchObject({ callId: "c1", status: "success", durationMs: 32, artifactIds: ["a1"] });
    expect(state.artifacts[0].id).toBe("a1");
    expect(state.approval).toBeNull();
    expect(state.terminal).toBe(true);
    expect(state.lastEventId).toBe(8);
  });

  it("按 event_id 去重，重复 token 不会重复追加", () => {
    let state = createRun("s1", "m1");
    const token = event(1, { event: "token", delta: "唯一" });
    state = applyEvent(state, token);
    const unchanged = applyEvent(state, token);
    expect(unchanged).toBe(state);
    expect(unchanged.content).toBe("唯一");
  });

  it("EVENT_GAP 清空临时快照并要求历史恢复", () => {
    let state = createRun("s1", "m1");
    state = applyEvent(state, event(1, { event: "token", delta: "临时内容" }));
    state = applyEvent(state, event(1, { event: "error", code: "EVENT_GAP", message: "缓存过期", retryable: false }));
    expect(state.content).toBe("");
    expect(state.needsHistory).toBe(true);
    expect(state.terminal).toBe(true);
    expect(state.lastEventId).toBe(1);
  });

  it("从历史 JSON 恢复工具卡，旧数据也有成功状态", () => {
    const tools = toolsFromHistory([{ tool: "aggregate_plays", params: {}, summary: "完成", artifact_ids: ["a1"] }]);
    expect(tools[0]).toMatchObject({ status: "success", artifactIds: ["a1"] });
  });
});
