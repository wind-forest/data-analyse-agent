import { describe, expect, it } from "vitest";
import { assistantView } from "./MessageBubble";
import { artifactsForMessage } from "./MessageList";
import { applyEvent, createRun } from "../../store/runReducer";
import type { Artifact, Message } from "../../types/api";

const message: Message = { id: "m1", session_id: "s1", role: "assistant", content: "最终结论", tool_calls_json: [{ call_id: "c1", tool: "profile_dataset", params: {}, status: "success", artifact_ids: ["a1"] }], finish_reason: "completed", created_at: "now" };
const artifact: Artifact = { id: "a1", run_id: "r1", message_id: "m1", type: "table", payload_json: { rows: [] }, file_path: null, created_at: "now" };

describe("历史与流式状态合并", () => {
  it("完成后以历史快照为准，正文与工具不重复", () => {
    let run = createRun("s1", "m1");
    run = applyEvent(run, { event_id: 1, message_id: "m1", timestamp: "now", event: "token", delta: "最终结论" });
    run = applyEvent(run, { event_id: 2, message_id: "m1", timestamp: "now", event: "artifact", artifact_id: "a1", type: "table", payload: { rows: [] } });
    run = { ...run, terminal: true };
    const view = assistantView(message, run);
    expect(view.content).toBe("最终结论");
    expect(view.tools).toHaveLength(1);
    expect(artifactsForMessage(message, run, [artifact])).toHaveLength(1);
  });

  it("EVENT_GAP 使用历史内容替换临时正文", () => {
    const run = { ...createRun("s1", "m1"), content: "重复临时", needsHistory: true, terminal: true };
    expect(assistantView(message, run).content).toBe("最终结论");
  });
});
