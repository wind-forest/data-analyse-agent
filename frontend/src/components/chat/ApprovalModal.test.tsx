import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApprovalModal } from "./ApprovalModal";
import type { ApprovalRequiredEvent } from "../../types/events";

const approval: ApprovalRequiredEvent = { event: "approval_required", event_id: 1, message_id: "m1", timestamp: "now", approval_id: "a1", run_id: "r1", tool: "execute_python_snippet", params: { code: "print(1)" }, expires_in_seconds: 600 };

describe("ApprovalModal", () => {
  it("展示代码并支持批准、拒绝", () => {
    const onDecision = vi.fn();
    render(<ApprovalModal approval={approval} pending={false} error={null} onDecision={onDecision} />);
    expect(screen.getByText(/print\(1\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "批准并继续" }));
    fireEvent.click(screen.getByRole("button", { name: "拒绝执行" }));
    expect(onDecision.mock.calls.map(([value]) => value)).toEqual(["approved", "rejected"]);
  });
  it("提交中禁用操作且不允许 Escape 误关闭", () => {
    render(<ApprovalModal approval={approval} pending error={null} onDecision={vi.fn()} />);
    expect(screen.getByRole("button", { name: "正在提交…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "拒绝执行" })).toBeDisabled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
