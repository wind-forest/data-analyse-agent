import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";
import type { Session } from "../../types/api";

const session: Session = { id: "s1", title: "音乐分析", summary: null, created_at: "now", updated_at: "2026-01-01" };

describe("Sidebar", () => {
  it("删除会话前必须确认", () => {
    const onDelete = vi.fn();
    render(<Sidebar sessions={[session]} onCreate={vi.fn()} onDelete={onDelete} creating={false} />);
    fireEvent.click(screen.getByRole("button", { name: "删除会话 音乐分析" }));
    expect(onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    expect(onDelete).toHaveBeenCalledWith("s1");
  });
});
