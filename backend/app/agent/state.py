from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    session_id: str
    message_id: str
    file_ids: list[str]
    messages: Annotated[list[AnyMessage], add_messages]
    iteration: int
    tool_history: list[dict[str, Any]]
    token_used: int
    pending_approval: dict[str, Any] | None
    artifacts: list[str]
    finish_reason: str | None
    termination_detail: str | None
    partial_answer: str | None
    model: str
    allow_custom_code: bool
    started_at: float
    deadline: float
