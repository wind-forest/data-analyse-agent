import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, FileSpreadsheet, Loader2, Paperclip, RotateCcw, Trash2, XCircle } from "lucide-react";
import { api } from "../../api/endpoints";
import { ApiError, uploadWithProgress } from "../../api/client";
import { queryKeys } from "../../queries";
import { useChatStore } from "../../store/chatStore";
import type { AppConfig, DataFile } from "../../types/api";
import { cn, formatBytes } from "../../utils/format";
import { Button } from "../ui/button";

interface UploadItem {
  key: number;
  file: File;
  progress: number;
  error: string | null;
}

interface FileUploadProps {
  sessionId: string;
  files: DataFile[];
  config?: AppConfig;
}

const statusText = { uploading: "上传中", validating: "校验中", ready: "就绪", failed: "失败" };

export function FileUpload({ sessionId, files, config }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const retryFiles = useRef(new Map<string, File>());
  const retryTarget = useRef<string | null>(null);
  const key = useRef(0);
  const queryClient = useQueryClient();
  const selected = useChatStore((state) => state.selectedFileIds);
  const toggleFile = useChatStore((state) => state.toggleFile);
  const setSelectedFiles = useChatStore((state) => state.setSelectedFiles);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);

  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.files(sessionId) });

  const upload = async (file: File, itemKey: number, replaceId?: string) => {
    const update = (values: Partial<UploadItem>) => setUploads((items) => items.map((item) => item.key === itemKey ? { ...item, ...values } : item));
    try {
      const uploaded = await uploadWithProgress(sessionId, file, (progress) => update({ progress }));
      if (uploaded.status === "ready") retryFiles.current.set(uploaded.id, file);
      if (replaceId && replaceId !== uploaded.id) await api.deleteFile(sessionId, replaceId).catch(() => undefined);
      setUploads((items) => items.filter((item) => item.key !== itemKey));
      await refresh();
      if (uploaded.status === "ready" && !useChatStore.getState().selectedFileIds.includes(uploaded.id)) toggleFile(uploaded.id);
    } catch (error) {
      update({ error: error instanceof ApiError ? error.message : "上传失败，请重试" });
    }
  };

  const startUpload = (file: File, replaceId?: string) => {
    const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
    const itemKey = ++key.current;
    const item = { key: itemKey, file, progress: 0, error: null };
    setUploads((items) => [...items, item]);
    if (![".csv", ".tsv", ".xlsx"].includes(extension)) {
      setUploads((items) => items.map((current) => current.key === itemKey ? { ...current, error: "仅支持 CSV、TSV 或 XLSX 文件" } : current));
      return;
    }
    if (config && file.size > config.max_upload_size_mb * 1024 * 1024) {
      setUploads((items) => items.map((current) => current.key === itemKey ? { ...current, error: `文件不能超过 ${config.max_upload_size_mb} MB` } : current));
      return;
    }
    void upload(file, itemKey, replaceId);
  };

  const remove = async (id: string) => {
    setDeleting(id);
    try {
      await api.deleteFile(sessionId, id);
      setSelectedFiles(selected.filter((item) => item !== id));
      await refresh();
    } finally {
      setDeleting(null);
    }
  };

  const retry = (file: DataFile) => {
    const raw = retryFiles.current.get(file.id);
    if (raw) startUpload(raw, file.id);
    else {
      retryTarget.current = file.id;
      inputRef.current?.click();
    }
  };

  return (
    <div className="px-1 pt-1">
      <input ref={inputRef} type="file" accept=".csv,.tsv,.xlsx" className="hidden" onChange={(event) => {
        const file = event.target.files?.[0];
        if (file) startUpload(file, retryTarget.current || undefined);
        retryTarget.current = null;
        event.target.value = "";
      }} />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => { retryTarget.current = null; inputRef.current?.click(); }}><Paperclip className="h-4 w-4" />添加数据</Button>
        <span className="text-xs text-neutral-400">CSV / TSV / XLSX{config ? `，最大 ${config.max_upload_size_mb} MB` : ""}</span>
      </div>
      {(files.length > 0 || uploads.length > 0) && <div className="mt-2 flex max-h-32 flex-wrap gap-2 overflow-y-auto pb-1">
        {files.map((file) => <div key={file.id} className={cn("flex max-w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-xs", file.status === "ready" && selected.includes(file.id) ? "border-blue-300 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/40" : "border-neutral-200 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900")}>
          <button disabled={file.status !== "ready"} className="flex min-w-0 items-center gap-2 text-left" onClick={() => toggleFile(file.id)} aria-label={`${selected.includes(file.id) ? "取消选择" : "选择"}文件 ${file.original_name}`}>
            {file.status === "ready" && selected.includes(file.id) ? <Check className="h-4 w-4 shrink-0 text-blue-600" /> : file.status === "failed" ? <XCircle className="h-4 w-4 shrink-0 text-red-500" /> : <FileSpreadsheet className="h-4 w-4 shrink-0 text-neutral-500" />}
            <span className="min-w-0"><span className="block max-w-40 truncate font-medium sm:max-w-56">{file.original_name}</span><span className="text-neutral-500">{formatBytes(file.size)} · {statusText[file.status]}</span></span>
          </button>
          {file.status === "failed" && <Button variant="ghost" size="icon" className="h-6 w-6" aria-label={`重试 ${file.original_name}`} onClick={() => retry(file)}><RotateCcw className="h-3.5 w-3.5" /></Button>}
          <Button variant="ghost" size="icon" className="h-6 w-6" disabled={deleting === file.id} aria-label={`删除文件 ${file.original_name}`} onClick={() => void remove(file.id)}>{deleting === file.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}</Button>
          {file.error && <span className="w-full text-red-600">{file.error}</span>}
        </div>)}
        {uploads.map((item) => <div key={item.key} className="min-w-52 rounded-lg border border-neutral-200 px-3 py-2 text-xs dark:border-neutral-800">
          <div className="flex items-center gap-2"><Loader2 className={cn("h-4 w-4", !item.error && "animate-spin")} /><span className="max-w-48 truncate">{item.file.name}</span>{item.error && <Button size="sm" variant="ghost" onClick={() => startUpload(item.file)}>重试</Button>}</div>
          {item.error ? <p className="mt-1 text-red-600">{item.error}</p> : <div className="mt-2 h-1 rounded-full bg-neutral-200 dark:bg-neutral-800"><div className="h-full rounded-full bg-blue-600 transition-all" style={{ width: `${item.progress}%` }} /></div>}
        </div>)}
      </div>}
    </div>
  );
}
