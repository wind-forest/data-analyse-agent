from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.agent.state import AgentState
from app.config import settings

FINISH_REASONS = {"completed", "max_iterations", "timeout", "budget_exceeded"}

REASON_TEXT = {
    "max_iterations": "达到最大迭代次数",
    "timeout": "超过执行时间预算",
    "budget_exceeded": "超过 token 预算",
}


def canonical_hash(tool_name: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool_name, "args": arguments}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_duplicate_call(state: AgentState, tool_name: str, arguments: dict[str, Any]) -> bool:
    history = state.get("tool_history") or []
    if not history:
        return False
    return history[-1].get("hash") == canonical_hash(tool_name, arguments)


def should_stop(state: AgentState) -> str | None:
    if state.get("finish_reason"):
        return state["finish_reason"]
    if (state.get("iteration") or 0) >= settings.max_iterations:
        return "max_iterations"
    if state.get("deadline") and time.time() > state["deadline"]:
        return "timeout"
    if (state.get("token_used") or 0) >= settings.agent_token_budget:
        return "budget_exceeded"
    return None


def compose_partial_answer(state: AgentState) -> str:
    reason = state.get("finish_reason") or "cancelled"
    head = f"分析未完全结束（{REASON_TEXT.get(reason, reason)}）。"
    summaries = [
        item["summary"]
        for item in (state.get("tool_history") or [])
        if item.get("summary")
    ]
    if not summaries:
        return head + "当前没有已完成的分析步骤，请调整问题后重试。"
    steps = "\n".join(f"- {item}" for item in summaries[-5:])
    return f"{head}以下结论仅基于已完成的步骤：\n{steps}"
