import type { ApiErrorBody, DataFile } from "../types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function errorFrom(body: ApiErrorBody, status: number): ApiError {
  return new ApiError(
    body.error?.message || `请求失败（${status}）`,
    body.error?.code || "HTTP_ERROR",
    status,
    body.error?.details,
  );
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api${path}`, { ...init, headers, credentials: "include" });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw errorFrom(body, response.status);
  return body as T;
}

export function uploadWithProgress(
  sessionId: string,
  file: File,
  onProgress: (percent: number) => void,
  signal?: AbortSignal,
): Promise<DataFile> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("file", file);
    xhr.open("POST", "/api/files");
    xhr.withCredentials = true;
    xhr.responseType = "json";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new ApiError("网络错误，上传失败", "NETWORK_ERROR", 0));
    xhr.onabort = () => reject(new ApiError("上传已取消", "UPLOAD_ABORTED", 0));
    xhr.onload = () => {
      const body = xhr.response || {};
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as DataFile);
      else reject(errorFrom(body, xhr.status));
    };
    signal?.addEventListener("abort", () => xhr.abort(), { once: true });
    xhr.send(form);
  });
}
