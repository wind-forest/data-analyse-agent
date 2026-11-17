import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";
import { FileUpload } from "./FileUpload";
import { useChatStore } from "../../store/chatStore";
import type { DataFile } from "../../types/api";

const base = { session_id: "s1", size: 100, sha256: "x", mime: "text/csv", error: null, created_at: "now" };
const files: DataFile[] = [
  { ...base, id: "f1", original_name: "ready.csv", status: "ready" },
  { ...base, id: "f2", original_name: "checking.csv", status: "validating" },
  { ...base, id: "f3", original_name: "bad.csv", status: "failed", error: "字段错误" },
];

function renderUpload() {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}><FileUpload sessionId="s1" files={files} config={{ default_model: "deepseek", allowed_models: [], max_upload_size_mb: 10, custom_code_available: true }} /></QueryClientProvider>);
}

describe("FileUpload", () => {
  beforeEach(() => useChatStore.setState({ selectedFileIds: [] }));
  it("展示校验中、就绪、失败状态，只允许选择就绪文件", () => {
    renderUpload();
    expect(screen.getByText(/校验中/)).toBeInTheDocument();
    expect(screen.getByText(/失败/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择文件 checking.csv" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "选择文件 ready.csv" }));
    expect(useChatStore.getState().selectedFileIds).toEqual(["f1"]);
    expect(screen.getByRole("button", { name: "重试 bad.csv" })).toBeInTheDocument();
  });

  it("上传前拒绝不支持的格式", () => {
    const { container } = renderUpload();
    const input = container.querySelector('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [new File(["a"], "notes.txt")] } });
    expect(screen.getByText("仅支持 CSV、TSV 或 XLSX 文件")).toBeInTheDocument();
  });
});
