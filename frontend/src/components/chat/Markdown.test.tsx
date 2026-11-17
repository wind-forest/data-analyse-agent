import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./Markdown";

describe("Markdown", () => {
  it("支持 GFM，但不执行或渲染未清洗原始 HTML", () => {
    const { container } = render(<Markdown content={'**结论**\n\n<script>alert(1)</script>\n\n[链接](https://example.com)'} />);
    expect(screen.getByText("结论")).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByRole("link", { name: "链接" })).toHaveAttribute("rel", "noreferrer");
  });
});
