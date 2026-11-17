from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy import select

from app.agent.llm import chat_completion
from app.agent.state import AgentState
from app.agent.termination import (
    canonical_hash,
    compose_partial_answer,
    is_duplicate_call,
    should_stop,
)
from app.config import settings
from app.db.models import AnalysisRun, Artifact
from app.db.session import SessionLocal
from app.errors import AppError
from app.services import approval_service, memory_service, run_service, sse_bus
from app.tools.base import ToolContext
from app.tools.finish import FinishArgs
from app.tools.registry import agent_tool_schemas, execute_tool, tool_risk

logger = logging.getLogger("app.agent.nodes")

FINISH_NUDGE = (
    "请调用 finish 工具提交最终答案，不要在消息正文中直接输出最终回答。"
)


def _to_openai_messages(messages: list[AnyMessage]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, SystemMessage):
            payload.append({"role": "system", "content": message.content})
        elif isinstance(message, HumanMessage):
            payload.append({"role": "user", "content": message.content})
        elif isinstance(message, AIMessage):
            item: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(
                                call["args"] or {}, ensure_ascii=False
                            ),
                        },
                    }
                    for call in message.tool_calls
                ]
            payload.append(item)
        elif isinstance(message, ToolMessage):
            payload.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": str(message.content),
                }
            )
    return payload


async def agent_node(state: AgentState) -> dict[str, Any]:
    stop_reason = should_stop(state)
    if stop_reason:
        return {
            "finish_reason": stop_reason,
            "partial_answer": compose_partial_answer(
                {**state, "finish_reason": stop_reason}
            ),
        }

    next_iteration = (state.get("iteration") or 0) + 1
    await sse_bus.publish_event(
        state["message_id"],
        "status",
        {"stage": "thinking", "iteration": next_iteration},
    )
    await sse_bus.set_status(
        state["message_id"], stage="thinking", iteration=next_iteration
    )

    response = await chat_completion(
        state["model"],
        _to_openai_messages(state["messages"]),
        agent_tool_schemas(bool(state.get("allow_custom_code"))),
    )
    tool_calls = [
        {"id": call.id, "name": call.name, "args": call.arguments, "type": "tool_call"}
        for call in response.tool_calls
    ]
    ai_message = AIMessage(content=response.content, tool_calls=tool_calls)
    updates: dict[str, Any] = {
        "iteration": next_iteration,
        "token_used": (state.get("token_used") or 0) + response.total_tokens,
    }

    if not tool_calls:
        # 直接文本不作为正常退出，保留为部分答案并要求模型用 finish 提交
        updates["messages"] = [ai_message, HumanMessage(content=FINISH_NUDGE)]
        updates["partial_answer"] = response.content
    else:
        updates["messages"] = [ai_message]
    return updates


def route_after_agent(state: AgentState) -> str:
    if state.get("finish_reason"):
        return "finish"
    last = state["messages"][-1]
    calls = getattr(last, "tool_calls", None) or []
    if not calls:
        return "agent"
    if any(call["name"] == "finish" for call in calls):
        return "finish"
    if any(tool_risk(call["name"]) == "high" for call in calls):
        return "approval_gate"
    return "tool_executor"


async def tool_executor_node(state: AgentState) -> dict[str, Any]:
    last = state["messages"][-1]
    calls = getattr(last, "tool_calls", None) or []
    history = list(state.get("tool_history") or [])
    artifacts = list(state.get("artifacts") or [])
    deadline = state.get("deadline") or time.time()
    started_at = state.get("started_at") or time.time()
    outputs: list[ToolMessage] = []

    await sse_bus.publish_event(
        state["message_id"],
        "status",
        {"stage": "tool_running", "iteration": state.get("iteration") or 0},
    )

    for call in calls:
        name = call["name"]
        arguments = call["args"] or {}
        call_hash = canonical_hash(name, arguments)

        if is_duplicate_call({**state, "tool_history": history}, name, arguments):
            outputs.append(
                ToolMessage(
                    content=json.dumps(
                        {"error": "duplicate_tool_call", "message": "重复调用相同工具和参数"},
                        ensure_ascii=False,
                    ),
                    tool_call_id=call["id"],
                )
            )
            return {
                "messages": outputs,
                "tool_history": history,
                "finish_reason": "max_iterations",
                "termination_detail": "duplicate_tool_call",
                "partial_answer": compose_partial_answer(
                    {
                        **state,
                        "tool_history": history,
                        "finish_reason": "max_iterations",
                    }
                ),
                "artifacts": artifacts,
            }

        started = time.perf_counter()
        run_id: str | None = None
        artifact_rows: list[Artifact] = []
        pending = state.get("pending_approval") or {}
        approved_run_id = (
            uuid.UUID(pending["run_id"])
            if pending.get("status") == "approved" and pending.get("call_id") == call["id"]
            else None
        )
        if approved_run_id is not None:
            # 审批阶段已建 run，复用执行时补发 tool_call 事件
            await sse_bus.publish_event(
                state["message_id"],
                "tool_call",
                {
                    "call_id": call["id"],
                    "run_id": str(approved_run_id),
                    "tool": name,
                    "params": arguments,
                },
            )
        async with SessionLocal() as db:
            context = ToolContext(
                db=db,
                session_id=uuid.UUID(state["session_id"]),
                message_id=uuid.UUID(state["message_id"]),
                run_id=approved_run_id,
            )
            with sse_bus.bind_event_context(state["message_id"], call["id"]):
                try:
                    result = await execute_tool(name, arguments, context)
                    content = result.model_dump_json()
                    new_ids = [str(item) for item in result.artifact_ids]
                    artifacts.extend(new_ids)
                    run_id = str(result.run_id)
                    tool_status = "success"
                    tool_summary = result.summary
                    tool_error = None
                    history.append(
                        {
                            "tool": name,
                            "params": arguments,
                            "hash": call_hash,
                            "summary": result.summary,
                            "artifact_ids": new_ids,
                        }
                    )
                    await memory_service.record_step(
                        state["session_id"],
                        tool=name,
                        params=arguments,
                        summary=result.summary,
                        artifact_ids=new_ids,
                    )
                    if result.artifact_ids:
                        artifact_rows = list(
                            await db.scalars(
                                select(Artifact).where(
                                    Artifact.id.in_(result.artifact_ids)
                                )
                            )
                        )
                except AppError as exc:
                    content = json.dumps(
                        {
                            "error": exc.code,
                            "message": exc.message,
                            "details": exc.details,
                        },
                        ensure_ascii=False,
                    )
                    tool_status = "failed"
                    tool_summary = f"{name} 失败：{exc.message}"
                    tool_error = exc.message
                    history.append(
                        {
                            "tool": name,
                            "params": arguments,
                            "hash": call_hash,
                            "summary": tool_summary,
                        }
                    )
                except Exception:
                    logger.exception("tool %s crashed", name)
                    content = json.dumps(
                        {"error": "TOOL_ERROR", "message": "工具执行异常"},
                        ensure_ascii=False,
                    )
                    tool_status = "failed"
                    tool_summary = f"{name} 执行异常"
                    tool_error = "工具执行异常"
                    history.append(
                        {
                            "tool": name,
                            "params": arguments,
                            "hash": call_hash,
                            "summary": tool_summary,
                        }
                    )

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        history[-1].update(
            {
                "call_id": call["id"],
                "run_id": run_id,
                "status": tool_status,
                "duration_ms": duration_ms,
                "error": tool_error,
                "artifact_ids": [str(row.id) for row in artifact_rows],
            }
        )
        await sse_bus.publish_event(
            state["message_id"],
            "tool_result",
            {
                "call_id": call["id"],
                "run_id": run_id,
                "status": tool_status,
                "summary": tool_summary,
                "artifact_ids": [
                    str(row.id) for row in artifact_rows
                ],
                "duration_ms": duration_ms,
                "error": tool_error,
            },
        )
        for artifact_row in artifact_rows:
            await sse_bus.publish_artifact(state["message_id"], artifact_row)

        outputs.append(ToolMessage(content=content, tool_call_id=call["id"]))

        if name == "train_predictive_model":
            deadline = max(deadline, started_at + settings.modeling_timeout_seconds)

    return {
        "messages": outputs,
        "tool_history": history,
        "artifacts": artifacts,
        "deadline": deadline,
    }


async def approval_gate_node(state: AgentState) -> dict[str, Any]:
    """高风险调用先落审批记录，再由 LangGraph 暂停等待用户决策。"""
    last = state["messages"][-1]
    calls = [
        call
        for call in (getattr(last, "tool_calls", None) or [])
        if tool_risk(call["name"]) == "high"
    ]
    if not calls:
        return {}

    call = calls[0]
    call_id = call["id"]
    arguments = dict(call["args"] or {})
    message_id = state["message_id"]
    session_id = uuid.UUID(state["session_id"])

    created = False
    async with SessionLocal() as db:
        found = await approval_service.find_by_call(
            db, uuid.UUID(message_id), call["name"], call_id
        )
        if found is not None:
            run, approval = found
        else:
            run = await run_service.start_run(
                db,
                session_id,
                call["name"],
                {**arguments, "__call_id__": call_id},
                message_id=uuid.UUID(message_id),
            )
            approval, created = await approval_service.create_pending(
                db,
                session_id=session_id,
                run_id=run.id,
                tool_name=call["name"],
                params=arguments,
            )
            run.status = "waiting_approval"
            await db.commit()

    if created:
        await sse_bus.publish_event(
            message_id,
            "approval_required",
            {
                "approval_id": str(approval.id),
                "run_id": str(run.id),
                "tool": call["name"],
                "params": arguments,
                "expires_in_seconds": settings.approval_timeout_seconds,
            },
        )
        await sse_bus.set_status(
            message_id, stage="approval", iteration=state.get("iteration") or 0
        )

    decision_value = interrupt(
        {
            "approval_id": str(approval.id),
            "run_id": str(run.id),
            "tool": call["name"],
            "params": arguments,
            "call_id": call_id,
            "expires_in_seconds": settings.approval_timeout_seconds,
        }
    )
    payload = decision_value if isinstance(decision_value, dict) else {}
    decision = payload.get("decision", "rejected")
    approved = decision == "approved"
    logger.info(
        "approval resume approval_id=%s decision=%s", approval.id, decision
    )

    await approval_service.apply_resume_decision(
        approval.id, "approved" if approved else "rejected"
    )

    if approved:
        return {
            "pending_approval": {
                "status": "approved",
                "tool": call["name"],
                "run_id": str(run.id),
                "call_id": call_id,
            }
        }

    async with SessionLocal() as db:
        run_row = await db.get(AnalysisRun, run.id)
        if run_row is not None:
            run_row.status = "failed"
            run_row.error = "用户拒绝执行"
            run_row.finished_at = datetime.now(UTC)
            await db.commit()

    rejection_messages = [
        ToolMessage(
            content=json.dumps(
                {
                    "error": "APPROVAL_REJECTED",
                    "message": "用户拒绝执行该操作，请改用低风险工具或调整方案",
                },
                ensure_ascii=False,
            ),
            tool_call_id=item["id"],
        )
        for item in (getattr(last, "tool_calls", None) or [])
    ]
    return {
        "messages": rejection_messages,
        "pending_approval": {"status": "rejected", "tool": call["name"]},
    }


def route_after_approval(state: AgentState) -> str:
    pending = state.get("pending_approval")
    if pending and pending.get("status") == "rejected":
        return "agent"
    return "tool_executor"


async def finish_node(state: AgentState) -> dict[str, Any]:
    await sse_bus.publish_event(
        state["message_id"],
        "status",
        {"stage": "finishing", "iteration": state.get("iteration") or 0},
    )
    answer = (state.get("partial_answer") or "").strip()
    collected = list(state.get("artifacts") or [])
    reason = state.get("finish_reason") or "completed"

    last = state["messages"][-1]
    for call in getattr(last, "tool_calls", None) or []:
        if call["name"] != "finish":
            continue
        try:
            args = FinishArgs.model_validate(call["args"])
        except ValidationError:
            logger.warning("finish arguments invalid")
            continue
        answer = args.answer.strip()
        allowed = {str(item) for item in args.artifact_ids}
        collected = [item for item in collected if item in allowed] if allowed else []

    if not answer:
        answer = compose_partial_answer({**state, "finish_reason": reason})

    return {
        "partial_answer": answer,
        "finish_reason": reason,
        "artifacts": collected,
    }
