import type { ArtifactType } from "./api";

interface EventBase {
  event_id: number;
  message_id: string;
  timestamp: string;
}

export interface StatusEvent extends EventBase {
  event: "status";
  stage: string;
  iteration: number;
}

export interface TokenEvent extends EventBase {
  event: "token";
  delta: string;
}

export interface ToolCallEvent extends EventBase {
  event: "tool_call";
  call_id: string;
  run_id: string | null;
  tool: string;
  params: Record<string, unknown>;
  started_at?: string | null;
}

export interface ToolResultEvent extends EventBase {
  event: "tool_result";
  call_id: string;
  run_id: string | null;
  status: "success" | "failed";
  summary: string;
  artifact_ids: string[];
  duration_ms: number;
  error: string | null;
}

export interface ArtifactEvent extends EventBase {
  event: "artifact";
  artifact_id: string;
  type: ArtifactType;
  payload: Record<string, unknown> | null;
}

export interface ApprovalRequiredEvent extends EventBase {
  event: "approval_required";
  approval_id: string;
  run_id: string;
  tool: string;
  params: Record<string, unknown>;
  expires_in_seconds: number;
}

export interface DoneEvent extends EventBase {
  event: "done";
  finish_reason: string;
}

export interface ErrorEvent extends EventBase {
  event: "error";
  code: string;
  message: string;
  retryable: boolean;
}

export type AnalysisEvent =
  | StatusEvent
  | TokenEvent
  | ToolCallEvent
  | ToolResultEvent
  | ArtifactEvent
  | ApprovalRequiredEvent
  | DoneEvent
  | ErrorEvent;

export type AnalysisEventName = AnalysisEvent["event"];

export const ANALYSIS_EVENT_NAMES: AnalysisEventName[] = [
  "status",
  "token",
  "tool_call",
  "tool_result",
  "artifact",
  "approval_required",
  "done",
  "error",
];
