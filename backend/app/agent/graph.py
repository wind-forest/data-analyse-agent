from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    agent_node,
    approval_gate_node,
    finish_node,
    route_after_agent,
    route_after_approval,
    tool_executor_node,
)
from app.agent.state import AgentState
from app.config import settings
from app.errors import AppError

logger = logging.getLogger("app.agent.graph")

_graph: Any | None = None
_graph_saver: Any | None = None


def build_graph(saver: Any) -> Any:
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tool_executor", tool_executor_node)
    builder.add_node("approval_gate", approval_gate_node)
    builder.add_node("finish", finish_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "agent": "agent",
            "tool_executor": "tool_executor",
            "approval_gate": "approval_gate",
            "finish": "finish",
        },
    )
    builder.add_edge("tool_executor", "agent")
    builder.add_conditional_edges(
        "approval_gate",
        route_after_approval,
        {"tool_executor": "tool_executor", "agent": "agent"},
    )
    builder.add_edge("finish", END)

    return builder.compile(checkpointer=saver)


def get_graph() -> Any:
    from app.agent.checkpointer import get_saver

    saver = get_saver()
    if saver is None:
        raise AppError("AGENT_NOT_READY", "Agent 检查点未就绪，请稍后重试", 503)

    global _graph, _graph_saver
    if _graph is None or _graph_saver is not saver:
        _graph = build_graph(saver)
        _graph_saver = saver
        logger.info("agent graph compiled")
    return _graph


def reset_graph() -> None:
    global _graph, _graph_saver
    _graph = None
    _graph_saver = None


def graph_config(message_id: str) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": message_id},
        "recursion_limit": settings.agent_recursion_limit,
    }
