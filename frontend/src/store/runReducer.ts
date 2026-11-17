import type { ArtifactType, ToolHistory } from "../types/api";
import type { AnalysisEvent, ApprovalRequiredEvent } from "../types/events";

export interface ToolCardState {
  callId: string;
  runId: string | null;
  tool: string;
  params: Record<string, unknown>;
  status: "running" | "success" | "failed";
  summary: string;
  durationMs?: number;
  error: string | null;
  artifactIds: string[];
}

export interface StreamArtifact {
  id: string;
  type: ArtifactType;
  payload: Record<string, unknown> | null;
}

export interface RunState {
  sessionId: string;
  messageId: string;
  stage: string;
  content: string;
  tools: Record<string, ToolCardState>;
  toolOrder: string[];
  artifacts: StreamArtifact[];
  approval: ApprovalRequiredEvent | null;
  lastEventId: number;
  seenEventIds: number[];
  retryCount: number;
  terminal: boolean;
  needsHistory: boolean;
  error: string | null;
}

export function createRun(sessionId: string, messageId: string): RunState {
  return {
    sessionId,
    messageId,
    stage: "queued",
    content: "",
    tools: {},
    toolOrder: [],
    artifacts: [],
    approval: null,
    lastEventId: 0,
    seenEventIds: [],
    retryCount: 0,
    terminal: false,
    needsHistory: false,
    error: null,
  };
}

function orderedTools(tools: Record<string, ToolCardState>, toolOrder: string[]) {
  return toolOrder.map((id) => tools[id]).filter(Boolean);
}

export function toolsFromHistory(history: ToolHistory[] | null): ToolCardState[] {
  return (history || []).map((item, index) => ({
    callId: item.call_id || item.run_id || `history-${index}`,
    runId: item.run_id || null,
    tool: item.tool,
    params: item.params || {},
    status: item.status || (item.error ? "failed" : "success"),
    summary: item.summary || "",
    durationMs: item.duration_ms,
    error: item.error || null,
    artifactIds: item.artifact_ids || [],
  }));
}

export function applyEvent(state: RunState, event: AnalysisEvent): RunState {
  if (event.message_id !== state.messageId) return state;
  if (event.event === "error" && event.code === "EVENT_GAP") {
    return {
      ...createRun(state.sessionId, state.messageId),
      lastEventId: Math.max(state.lastEventId, event.event_id),
      seenEventIds: state.seenEventIds,
      stage: "restoring",
      terminal: true,
      needsHistory: true,
      error: event.message,
    };
  }
  if (state.seenEventIds.includes(event.event_id)) return state;
  const base: RunState = {
    ...state,
    lastEventId: Math.max(state.lastEventId, event.event_id),
    seenEventIds: [...state.seenEventIds.slice(-1999), event.event_id],
    retryCount: 0,
  };

  switch (event.event) {
    case "status":
      return { ...base, stage: event.stage, approval: null };
    case "token":
      return { ...base, content: base.content + event.delta };
    case "tool_call": {
      const previous = base.tools[event.call_id];
      return {
        ...base,
        approval: null,
        tools: {
          ...base.tools,
          [event.call_id]: {
            callId: event.call_id,
            runId: event.run_id,
            tool: event.tool,
            params: event.params,
            status: "running",
            summary: previous?.summary || "正在执行",
            error: null,
            artifactIds: previous?.artifactIds || [],
          },
        },
        toolOrder: previous ? base.toolOrder : [...base.toolOrder, event.call_id],
      };
    }
    case "tool_result": {
      const key = event.call_id || event.run_id || `result-${event.event_id}`;
      const previous = base.tools[key];
      const card: ToolCardState = {
        callId: key,
        runId: event.run_id,
        tool: previous?.tool || "工具执行",
        params: previous?.params || {},
        status: event.status,
        summary: event.summary,
        durationMs: event.duration_ms,
        error: event.error,
        artifactIds: event.artifact_ids || [],
      };
      return {
        ...base,
        tools: { ...base.tools, [key]: card },
        toolOrder: previous ? base.toolOrder : [...base.toolOrder, key],
      };
    }
    case "artifact":
      return base.artifacts.some((item) => item.id === event.artifact_id)
        ? base
        : {
            ...base,
            artifacts: [
              ...base.artifacts,
              { id: event.artifact_id, type: event.type, payload: event.payload },
            ],
          };
    case "approval_required":
      return { ...base, approval: event, stage: "approval" };
    case "done":
      return { ...base, stage: "done", terminal: true, approval: null, error: null };
    case "error":
      if (event.code === "EVENT_GAP") {
        return {
          ...createRun(base.sessionId, base.messageId),
          lastEventId: base.lastEventId,
          seenEventIds: base.seenEventIds,
          stage: "restoring",
          terminal: true,
          needsHistory: true,
          error: event.message,
        };
      }
      return { ...base, stage: "error", terminal: true, approval: null, error: event.message };
  }
}

export function visibleTools(run: RunState): ToolCardState[] {
  return orderedTools(run.tools, run.toolOrder);
}
