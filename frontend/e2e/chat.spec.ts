import { expect, test, type Page, type Route } from "@playwright/test";
import type {
  Artifact,
  DataFile,
  Message,
  MessagePayload,
  Session,
  ToolHistory,
} from "../src/types/api";

const TIMESTAMP = "2026-01-01T00:00:00.000Z";

interface TestEvent {
  event_id: number;
  message_id: string;
  event: string;
  [key: string]: unknown;
}

interface StreamRequest {
  sessionId: string;
  messageId: string;
  attempt: number;
  lastEventId: number;
}

interface Backend {
  sessions: Session[];
  messages: Record<string, Message[]>;
  files: Record<string, DataFile[]>;
  artifacts: Record<string, Artifact[]>;
  sent: MessagePayload[];
  uploads: string[];
  decisions: Array<{ approvalId: string; decision: "approved" | "rejected" }>;
  streams: StreamRequest[];
}

interface MockOptions {
  sessions?: Session[];
  messages?: Record<string, Message[]>;
  files?: Record<string, DataFile[]>;
  artifacts?: Record<string, Artifact[]>;
  messageId?: (payload: MessagePayload, index: number) => string;
  stream: (request: StreamRequest, backend: Backend) => string | Promise<string>;
}

function sse(events: TestEvent[]): string {
  return events
    .map((event) => [
      `id: ${event.event_id}`,
      `event: ${event.event}`,
      `data: ${JSON.stringify({ timestamp: TIMESTAMP, ...event })}`,
      "",
      "",
    ].join("\n"))
    .join("");
}

function makeSession(id = "session-1", title = "既有分析"): Session {
  return {
    id,
    title,
    summary: "Playwright 模拟会话",
    created_at: TIMESTAMP,
    updated_at: TIMESTAMP,
  };
}

function makeFile(id: string, sessionId: string, originalName: string): DataFile {
  return {
    id,
    session_id: sessionId,
    original_name: originalName,
    size: 128,
    sha256: `sha256-${id}`,
    mime: "text/csv",
    status: "ready",
    error: null,
    created_at: TIMESTAMP,
  };
}

function makeChart(id: string, messageId: string): Artifact {
  return {
    id,
    run_id: "run-chart",
    message_id: messageId,
    type: "chart",
    payload_json: {
      chart_type: "bar",
      x: "月份",
      y: "销售额",
      data: {
        x: ["1 月", "2 月"],
        series: [{ name: "销售额", data: [12, 18] }],
      },
      meta: { title: "月度销售额", unit: "万元" },
    },
    file_path: null,
    created_at: TIMESTAMP,
  };
}

function json(route: Route, body: unknown, status = 200): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json; charset=utf-8",
    body: JSON.stringify(body),
  });
}

async function mockApi(page: Page, options: MockOptions): Promise<Backend> {
  const backend: Backend = {
    sessions: options.sessions ?? [],
    messages: options.messages ?? {},
    files: options.files ?? {},
    artifacts: options.artifacts ?? {},
    sent: [],
    uploads: [],
    decisions: [],
    streams: [],
  };
  const attempts = new Map<string, number>();

  for (const session of backend.sessions) {
    backend.messages[session.id] ??= [];
    backend.files[session.id] ??= [];
    backend.artifacts[session.id] ??= [];
  }

  await page.route((url) => url.pathname.startsWith("/api/"), async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");

    if (method === "GET" && path === "/config") {
      return json(route, {
        default_model: "test-model",
        allowed_models: ["test-model", "test-model-fast"],
        max_upload_size_mb: 10,
        custom_code_available: true,
      });
    }

    if (path === "/sessions" && method === "GET") {
      return json(route, backend.sessions);
    }

    if (path === "/sessions" && method === "POST") {
      const payload = request.postDataJSON() as { title?: string };
      const created = makeSession(`created-${backend.sessions.length + 1}`, payload.title || "新分析");
      backend.sessions.push(created);
      backend.messages[created.id] = [];
      backend.files[created.id] = [];
      backend.artifacts[created.id] = [];
      return json(route, created, 201);
    }

    const streamMatch = /^\/sessions\/([^/]+)\/stream$/.exec(path);
    if (streamMatch && method === "GET") {
      const sessionId = decodeURIComponent(streamMatch[1]);
      const messageId = url.searchParams.get("message_id") || "";
      const key = `${sessionId}:${messageId}`;
      const attempt = (attempts.get(key) || 0) + 1;
      attempts.set(key, attempt);
      const streamRequest: StreamRequest = {
        sessionId,
        messageId,
        attempt,
        lastEventId: Number(url.searchParams.get("last_event_id") || 0),
      };
      backend.streams.push(streamRequest);
      const body = await options.stream(streamRequest, backend);
      return route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache",
          Connection: "keep-alive",
        },
        body,
      });
    }

    const messagesMatch = /^\/sessions\/([^/]+)\/messages$/.exec(path);
    if (messagesMatch && method === "GET") {
      return json(route, backend.messages[decodeURIComponent(messagesMatch[1])] || []);
    }

    if (messagesMatch && method === "POST") {
      const sessionId = decodeURIComponent(messagesMatch[1]);
      const payload = request.postDataJSON() as MessagePayload;
      const index = backend.sent.length;
      const messageId = options.messageId?.(payload, index) ?? `analysis-${index + 1}`;
      backend.sent.push(payload);
      backend.messages[sessionId] ??= [];
      backend.messages[sessionId].push(
        {
          id: `user-${index + 1}`,
          session_id: sessionId,
          role: "user",
          content: payload.content,
          tool_calls_json: null,
          finish_reason: null,
          created_at: TIMESTAMP,
        },
        {
          id: messageId,
          session_id: sessionId,
          role: "assistant",
          content: "",
          tool_calls_json: null,
          finish_reason: null,
          created_at: TIMESTAMP,
        },
      );
      return json(route, { message_id: messageId }, 202);
    }

    const artifactsMatch = /^\/sessions\/([^/]+)\/artifacts$/.exec(path);
    if (artifactsMatch && method === "GET") {
      return json(route, backend.artifacts[decodeURIComponent(artifactsMatch[1])] || []);
    }

    if (path === "/files" && method === "GET") {
      return json(route, backend.files[url.searchParams.get("session_id") || ""] || []);
    }

    if (path === "/files" && method === "POST") {
      const body = request.postData() || "";
      const sessionId = /name="session_id"\r?\n\r?\n([^\r\n]+)/.exec(body)?.[1]
        || backend.sessions[0]?.id
        || "session-1";
      const originalName = /filename="([^"]+)"/.exec(body)?.[1]
        || (backend.uploads.length === 0 ? "sales.csv" : "regions.csv");
      const uploaded = makeFile(`file-${backend.uploads.length + 1}`, sessionId, originalName);
      backend.uploads.push(originalName);
      backend.files[sessionId] ??= [];
      backend.files[sessionId].push(uploaded);
      return json(route, uploaded, 201);
    }

    const approvalMatch = /^\/approvals\/([^/]+)$/.exec(path);
    if (approvalMatch && method === "POST") {
      const approvalId = decodeURIComponent(approvalMatch[1]);
      const payload = request.postDataJSON() as { decision: "approved" | "rejected" };
      backend.decisions.push({ approvalId, decision: payload.decision });
      return json(route, {
        approval_id: approvalId,
        status: payload.decision,
        message_id: "approval-message",
      });
    }

    return json(route, {
      error: { code: "NOT_MOCKED", message: `未模拟 ${method} ${path}` },
    }, 404);
  });

  return backend;
}

function completeMessage(
  backend: Backend,
  sessionId: string,
  messageId: string,
  content: string,
  tools: ToolHistory[] = [],
  artifacts: Artifact[] = [],
): void {
  const message = backend.messages[sessionId]?.find((item) => item.id === messageId);
  if (!message) throw new Error(`找不到模拟消息 ${messageId}`);
  message.content = content;
  message.tool_calls_json = tools;
  message.finish_reason = "stop";
  backend.artifacts[sessionId] = [
    ...(backend.artifacts[sessionId] || []),
    ...artifacts,
  ];
}

for (const mode of ["new", "existing"] as const) {
  test(`${mode === "new" ? "新建" : "已有"}会话：两个 CSV、工具、Markdown、图表与追问`, async ({ page }) => {
    const backend = await mockApi(page, {
      sessions: mode === "existing" ? [makeSession()] : [],
      stream: (stream, api) => {
        if (stream.messageId === "analysis-1") {
          const chart = makeChart("chart-1", stream.messageId);
          const history: ToolHistory = {
            call_id: "call-aggregate",
            run_id: "run-aggregate",
            tool: "aggregate_plays",
            params: { file_ids: ["file-1", "file-2"], group_by: "month" },
            status: "success",
            summary: "已汇总两个 CSV 的月度销售额",
            duration_ms: 128,
            error: null,
            artifact_ids: [chart.id],
          };
          completeMessage(
            api,
            stream.sessionId,
            stream.messageId,
            "**分析结论**：两个月销售额持续增长。",
            [history],
            [chart],
          );
          return sse([
            { event_id: 1, message_id: stream.messageId, event: "status", stage: "tool_running", iteration: 1 },
            {
              event_id: 2,
              message_id: stream.messageId,
              event: "tool_call",
              call_id: "call-aggregate",
              run_id: "run-aggregate",
              tool: "aggregate_plays",
              params: history.params,
              started_at: TIMESTAMP,
            },
            {
              event_id: 3,
              message_id: stream.messageId,
              event: "tool_result",
              call_id: "call-aggregate",
              run_id: "run-aggregate",
              status: "success",
              summary: history.summary!,
              artifact_ids: [chart.id],
              duration_ms: 128,
              error: null,
            },
            { event_id: 4, message_id: stream.messageId, event: "token", delta: "**分析结论**：" },
            { event_id: 5, message_id: stream.messageId, event: "token", delta: "两个月销售额持续增长。" },
            {
              event_id: 6,
              message_id: stream.messageId,
              event: "artifact",
              artifact_id: chart.id,
              type: "chart",
              payload: chart.payload_json,
            },
            { event_id: 7, message_id: stream.messageId, event: "done", finish_reason: "stop" },
          ]);
        }

        completeMessage(
          api,
          stream.sessionId,
          stream.messageId,
          "`华东` 增长最快，增幅为 **18%**。",
        );
        return sse([
          {
            event_id: 1,
            message_id: stream.messageId,
            event: "token",
            delta: "`华东` 增长最快，增幅为 **18%**。",
          },
          { event_id: 2, message_id: stream.messageId, event: "done", finish_reason: "stop" },
        ]);
      },
    });

    await page.goto("/");
    if (mode === "new") {
      await page.locator("main").getByRole("button", { name: "新建分析", exact: true }).click();
    }
    await expect(page.getByRole("heading", { name: "今天想分析什么？" })).toBeVisible();

    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: "sales.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("month,sales\n2026-01,12\n2026-02,18\n"),
    });
    await expect(page.getByRole("button", { name: "取消选择文件 sales.csv", exact: true })).toBeVisible();
    await fileInput.setInputFiles({
      name: "regions.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("region,growth\n华东,0.18\n华北,0.08\n"),
    });
    await expect(page.getByRole("button", { name: "取消选择文件 regions.csv", exact: true })).toBeVisible();
    expect(backend.uploads).toEqual(["sales.csv", "regions.csv"]);

    const composer = page.getByRole("textbox", { name: "分析问题的数据" });
    await expect(page.getByRole("combobox", { name: "选择模型" })).toContainText("test-model");
    await composer.fill("比较两个月的销售表现并生成图表");
    await page.getByRole("button", { name: "发送问题" }).click();

    const firstMessage = page.locator("#message-analysis-1");
    await expect(firstMessage.locator(".markdown")).toContainText("两个月销售额持续增长。");
    await expect(firstMessage.locator(".markdown strong")).toHaveText("分析结论");
    const toolCard = firstMessage.locator("details");
    await expect(toolCard).toContainText("聚合数据");
    await expect(toolCard).toContainText("已完成");
    await toolCard.locator("summary").click();
    await expect(toolCard).toContainText("已汇总两个 CSV 的月度销售额");
    await expect(firstMessage.locator("#artifact-chart-1")).toBeVisible();
    await expect(firstMessage.getByRole("img", { name: "分析图表" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await expect(page.getByRole("button", { name: "查看 1 个分析产物" })).toBeVisible();

    await composer.fill("哪个地区增长最快？");
    await composer.press("Enter");
    const followUp = page.locator("#message-analysis-2");
    await expect(followUp.locator(".markdown")).toContainText("增长最快");
    await expect(followUp.locator(".markdown code")).toHaveText("华东");
    await expect(followUp.locator(".markdown strong")).toHaveText("18%");

    expect(backend.sent).toHaveLength(2);
    expect(backend.sent[0]).toMatchObject({
      content: "比较两个月的销售表现并生成图表",
      file_ids: ["file-1", "file-2"],
      model: "test-model",
      allow_custom_code: false,
    });
    expect(backend.sent[1]).toMatchObject({
      content: "哪个地区增长最快？",
      file_ids: ["file-1", "file-2"],
    });
  });
}

test("SSE 首次断开后携带 last_event_id 重连且忽略重复 token", async ({ page }) => {
  const backend = await mockApi(page, {
    sessions: [makeSession()],
    files: { "session-1": [makeFile("file-1", "session-1", "sales.csv")] },
    messageId: () => "reconnect-message",
    stream: (stream, api) => {
      if (stream.attempt === 1) {
        return sse([
          { event_id: 1, message_id: stream.messageId, event: "token", delta: "不会重复" },
        ]);
      }
      completeMessage(api, stream.sessionId, stream.messageId, "不会重复，已恢复");
      return sse([
        { event_id: 1, message_id: stream.messageId, event: "token", delta: "不会重复" },
        { event_id: 2, message_id: stream.messageId, event: "token", delta: "，已恢复" },
        { event_id: 3, message_id: stream.messageId, event: "done", finish_reason: "stop" },
      ]);
    },
  });

  await page.goto("/");
  await expect(page.getByRole("button", { name: "取消选择文件 sales.csv", exact: true })).toBeVisible();
  const composer = page.getByRole("textbox", { name: "分析问题的数据" });
  await expect(composer).toBeEditable();
  await composer.fill("验证断线恢复");
  const resumedRequest = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return url.pathname.endsWith("/stream") && url.searchParams.get("last_event_id") === "1";
  });
  await page.getByRole("button", { name: "发送问题" }).click();

  await expect(page.locator("#message-reconnect-message .markdown")).toContainText("不会重复");
  await resumedRequest;
  await expect(page.locator("#message-reconnect-message .markdown")).toHaveText("不会重复，已恢复");
  expect(backend.streams.map((stream) => stream.lastEventId)).toEqual([0, 1]);
});

for (const decision of ["approved", "rejected"] as const) {
  test(`approval_required 后${decision === "approved" ? "批准并继续" : "拒绝执行"}`, async ({ page }) => {
    const conclusion = decision === "approved"
      ? "自定义代码已获批并执行。"
      : "已拒绝执行，未运行自定义代码。";
    const backend = await mockApi(page, {
      sessions: [makeSession()],
      files: { "session-1": [makeFile("file-1", "session-1", "sales.csv")] },
      messageId: () => "approval-message",
      stream: (stream, api) => {
        if (!api.decisions.length) {
          return sse([
            {
              event_id: 1,
              message_id: stream.messageId,
              event: "approval_required",
              approval_id: "approval-1",
              run_id: "run-custom-code",
              tool: "execute_python_snippet",
              params: { code: "print(df.shape)" },
              expires_in_seconds: 300,
            },
          ]);
        }
        completeMessage(api, stream.sessionId, stream.messageId, conclusion);
        return sse([
          { event_id: 2, message_id: stream.messageId, event: "token", delta: conclusion },
          { event_id: 3, message_id: stream.messageId, event: "done", finish_reason: "stop" },
        ]);
      },
    });

    await page.goto("/");
    await expect(page.getByRole("button", { name: "取消选择文件 sales.csv", exact: true })).toBeVisible();
    const composer = page.getByRole("textbox", { name: "分析问题的数据" });
    await expect(composer).toBeEditable();
    const customCode = page.getByRole("checkbox");
    await customCode.check();
    await expect(customCode).toBeChecked();
    await composer.fill("用自定义代码检查数据维度");
    await page.getByRole("button", { name: "发送问题" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "需要批准高风险操作" })).toBeVisible();
    await expect(dialog.locator("pre")).toContainText("print(df.shape)");
    await dialog.getByRole("button", {
      name: decision === "approved" ? "批准并继续" : "拒绝执行",
      exact: true,
    }).click();

    await expect(dialog).toHaveCount(0);
    await expect(page.locator("#message-approval-message .markdown")).toHaveText(conclusion);
    expect(backend.decisions).toEqual([{ approvalId: "approval-1", decision }]);
    expect(backend.sent[0].allow_custom_code).toBe(true);
  });
}

test("产物可定位到原消息，刷新后恢复历史工具与图表", async ({ page }) => {
  const chart = makeChart("history-chart", "history-assistant");
  const history: ToolHistory = {
    call_id: "history-call",
    run_id: "history-run",
    tool: "generate_chart_data",
    params: { x: "month", y: "sales" },
    status: "success",
    summary: "已生成月度销售额图表",
    duration_ms: 86,
    error: null,
    artifact_ids: [chart.id],
  };
  const backend = await mockApi(page, {
    sessions: [makeSession()],
    messages: {
      "session-1": [
        {
          id: "history-user",
          session_id: "session-1",
          role: "user",
          content: "生成历史图表",
          tool_calls_json: null,
          finish_reason: null,
          created_at: TIMESTAMP,
        },
        {
          id: "history-assistant",
          session_id: "session-1",
          role: "assistant",
          content: "**历史结论**：图表来自历史消息。",
          tool_calls_json: [history],
          finish_reason: "stop",
          created_at: TIMESTAMP,
        },
      ],
    },
    artifacts: { "session-1": [chart] },
    stream: () => "",
  });

  await page.addInitScript(() => {
    localStorage.setItem("analysis-current-session", "session-1");
  });
  await page.goto("/");
  const historicalMessage = page.locator("#message-history-assistant");
  await expect(historicalMessage.locator(".markdown strong")).toHaveText("历史结论");
  await expect(historicalMessage.locator("#artifact-history-chart")).toBeVisible();

  await page.getByRole("button", { name: "查看 1 个分析产物" }).click();
  const drawer = page.getByRole("dialog", { name: "分析产物" });
  await expect(drawer).toBeVisible();
  await expect(drawer.locator("#artifact-history-chart")).toBeVisible();
  await drawer.getByRole("button", { name: "定位到原消息" }).click();
  await expect(drawer).toHaveCount(0);
  await expect(historicalMessage).toBeInViewport();

  await page.reload();
  await expect(historicalMessage.locator(".markdown strong")).toHaveText("历史结论");
  const toolCard = historicalMessage.locator("details");
  await expect(toolCard).toContainText("生成图表");
  await expect(toolCard).toContainText("已完成");
  await toolCard.locator("summary").click();
  await expect(toolCard).toContainText("已生成月度销售额图表");
  await expect(historicalMessage.locator("#artifact-history-chart")).toBeVisible();
  await expect(historicalMessage.getByRole("img", { name: "分析图表" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("analysis-current-session"))).toBe("session-1");
  expect(backend.streams).toEqual([]);
});

test("移动视口可操作侧栏、发送消息并持久化深色模式", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, {
    sessions: [makeSession()],
    files: { "session-1": [makeFile("file-1", "session-1", "mobile.csv")] },
    messageId: () => "mobile-message",
    stream: (stream, api) => {
      const conclusion = "移动端 **深色模式** 操作正常。";
      completeMessage(api, stream.sessionId, stream.messageId, conclusion);
      return sse([
        { event_id: 1, message_id: stream.messageId, event: "token", delta: conclusion },
        { event_id: 2, message_id: stream.messageId, event: "done", finish_reason: "stop" },
      ]);
    },
  });
  await page.addInitScript(() => {
    localStorage.setItem("analysis-current-session", "session-1");
    localStorage.setItem("analysis-theme", "dark");
  });
  await page.goto("/");

  await expect(page.getByRole("button", { name: "取消选择文件 mobile.csv", exact: true })).toBeVisible();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.locator("div.h-dvh")).toHaveCSS("background-color", "rgb(23, 23, 23)");
  expect(await page.evaluate(() => localStorage.getItem("analysis-theme"))).toBe("dark");
  await page.getByRole("button", { name: "打开会话列表" }).click();
  const closeSidebar = page.getByRole("button", { name: "关闭侧栏" });
  await expect(closeSidebar).toBeInViewport();
  await closeSidebar.click();

  await page.getByRole("button", { name: "切换浅色模式" }).click();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await expect(page.locator("div.h-dvh")).toHaveCSS("background-color", "rgb(255, 255, 255)");
  expect(await page.evaluate(() => localStorage.getItem("analysis-theme"))).toBe("light");
  await page.getByRole("button", { name: "切换深色模式" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  expect(await page.evaluate(() => localStorage.getItem("analysis-theme"))).toBe("dark");

  const composer = page.getByRole("textbox", { name: "分析问题的数据" });
  await composer.fill("在移动端分析数据");
  await composer.press("Enter");
  await expect(page.locator("#message-mobile-message .markdown strong")).toHaveText("深色模式");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
