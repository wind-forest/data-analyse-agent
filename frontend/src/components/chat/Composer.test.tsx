import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";
import { useChatStore } from "../../store/chatStore";
import type { DataFile } from "../../types/api";

const readyFile: DataFile = { id: "f1", session_id: "s1", original_name: "data.csv", size: 100, sha256: "x", mime: "text/csv", status: "ready", error: null, created_at: "now" };

describe("Composer", () => {
  beforeEach(() => useChatStore.setState({ draft: "分析数据", run: null, allowCustomCode: false }));
  it("Enter 发送，Shift+Enter 换行，IME 组合期间不发送", () => {
    const onSend = vi.fn();
    render(<Composer sessionId="s1" files={[readyFile]} sending={false} error={null} onSend={onSend} />);
    const input = screen.getByLabelText("分析问题的数据");
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.compositionStart(input);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("分析数据");
  });

  it("无就绪文件、空内容和运行中禁止发送", () => {
    const onSend = vi.fn();
    const { rerender } = render(<Composer sessionId="s1" files={[]} sending={false} error={null} onSend={onSend} />);
    expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
    useChatStore.setState({ draft: "" });
    rerender(<Composer sessionId="s1" files={[readyFile]} sending={false} error={null} onSend={onSend} />);
    expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
    useChatStore.setState({ draft: "问题" });
    useChatStore.getState().startRun("s1", "m1");
    rerender(<Composer sessionId="s1" files={[readyFile]} sending={false} error={null} onSend={onSend} />);
    expect(screen.getByRole("button", { name: "发送问题" })).toBeDisabled();
  });
});
