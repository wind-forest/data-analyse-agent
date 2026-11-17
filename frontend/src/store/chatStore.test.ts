import { beforeEach, describe, expect, it } from "vitest";
import { useChatStore } from "./chatStore";

describe("chatStore 主题", () => {
  beforeEach(() => {
    localStorage.clear();
    useChatStore.setState({ theme: "light" });
  });
  it("切换主题并保存偏好", () => {
    useChatStore.getState().toggleTheme();
    expect(useChatStore.getState().theme).toBe("dark");
    expect(localStorage.getItem("analysis-theme")).toBe("dark");
    useChatStore.getState().toggleTheme();
    expect(useChatStore.getState().theme).toBe("light");
  });
});
