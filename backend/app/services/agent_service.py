from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import get_graph, graph_config
from app.agent.prompts import FileBrief, build_system_prompt
from app.config import settings
from app.db.models import AnalysisRun, Approval, File, Message
from app.db.redis import get_redis
from app.db.session import SessionLocal
from app.errors import AppError
from app.schemas.messages import MessageCreate
from app.services import memory_service, session_service, sse_bus
from app.services.dataset_schema import detect_dataset
from app.services.storage import resolve_relative

logger = logging.getLogger("app.agent.service")

_background_tasks: set[asyncio.Task] = set()

KIND_LABELS = {
    "actions": "用户行为表",
    "songs": "歌曲信息表",
    "generic": "通用表格",
}


def _active_key(session_id: uuid.UUID) -> str:
    return f"session:{session_id}:active"


def _answer_chunks(text: str, size: int = 24) -> list[str]:
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


async def _acquire_active(session_id: uuid.UUID) -> bool:
    try:
        result = await get_redis().set(_active_key(session_id), "1", nx=True, ex=900)
        return bool(result)
    except Exception:  # noqa: BLE001 - Redis 不可用时降级为不加锁
        logger.warning("redis unavailable, skip active lock")
        return True


async def _release_active(session_id: uuid.UUID) -> None:
    try:
        await get_redis().delete(_active_key(session_id))
    except Exception:  # noqa: BLE001
        logger.warning("redis unavailable, skip active unlock")


def _brief(row: File) -> FileBrief:
    kind = "generic"
    try:
        kind = detect_dataset(resolve_relative(row.stored_path)).kind
    except Exception:
        logger.debug("dataset kind detection failed for %s", row.id, exc_info=True)
    return FileBrief(
        file_id=str(row.id),
        name=row.original_name,
        size_mb=round(row.size / 1024 / 1024, 2),
        kind=KIND_LABELS.get(kind, kind),
    )


async def _resolve_files(
    db: AsyncSession, session_id: uuid.UUID, requested: list[uuid.UUID]
) -> list[File]:
    rows = list(
        await db.scalars(
            select(File).where(File.session_id == session_id).order_by(File.created_at)
        )
    )
    ready = {row.id: row for row in rows if row.status == "ready"}

    if not requested:
        return list(ready.values())

    missing = [str(item) for item in requested if item not in ready]
    if missing:
        raise AppError(
            "FILE_NOT_FOUND", "指定的文件不属于当前会话或尚未就绪", 404,
            {"file_ids": missing},
        )
    return [ready[item] for item in requested]


async def _history(db: AsyncSession, session_id: uuid.UUID) -> list[Message]:
    rows = list(
        await db.scalars(
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.content != "",
                Message.finish_reason != "failed",
            )
            .order_by(Message.created_at.desc())
            .limit(8)
        )
    )
    rows.reverse()
    return rows


async def submit_message(
    db: AsyncSession, session_id: uuid.UUID, payload: MessageCreate
) -> Message:
    session = await session_service.get_session(db, session_id)

    content = payload.content.strip()
    if not content:
        raise AppError("VALIDATION_ERROR", "问题内容不能为空", 422)

    model = payload.model or settings.model_name
    if model not in settings.allowed_model_list:
        raise AppError(
            "MODEL_NOT_ALLOWED",
            f"模型 {model} 不在允许列表中",
            400,
            {"allowed_models": settings.allowed_model_list},
        )

    if not settings.llm_configured:
        raise AppError("LLM_NOT_CONFIGURED", "未配置 DeepSeek API Key，无法执行分析", 503)

    files = await _resolve_files(db, session_id, payload.file_ids)
    if not files:
        raise AppError("FILE_REQUIRED", "请先上传要分析的数据文件", 400)

    if not await _acquire_active(session_id):
        raise AppError("MESSAGE_RUNNING", "当前会话已有一条消息在执行", 409)

    try:
        history = await _history(db, session_id)
        user_message = Message(session_id=session_id, role="user", content=content)
        assistant_message = Message(
            session_id=session_id, role="assistant", content=""
        )
        db.add_all([user_message, assistant_message])
        await db.commit()
        await db.refresh(user_message)
        await db.refresh(assistant_message)
        await session_service.touch_session(db, session)
    except Exception:
        await _release_active(session_id)
        raise

    await sse_bus.publish_event(
        assistant_message.id, "status", {"stage": "queued", "iteration": 0}
    )
    await sse_bus.set_status(assistant_message.id, stage="queued")

    task = asyncio.create_task(
        _run_agent(
            message_id=assistant_message.id,
            session_id=session_id,
            content=content,
            files=files,
            history=history,
            model=model,
            allow_custom_code=payload.allow_custom_code,
        )
    )
    _track(task)
    return assistant_message


def _build_state(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    content: str,
    files: list[File],
    history: list[Message],
    model: str,
    allow_custom_code: bool,
) -> dict:
    now = datetime.now(UTC).timestamp()
    messages: list = [
        SystemMessage(
            content=build_system_prompt(
                [_brief(row) for row in files], allow_custom_code
            )
        )
    ]
    for item in history:
        if item.role == "user":
            messages.append(HumanMessage(content=item.content))
        else:
            messages.append(AIMessage(content=item.content))
    messages.append(HumanMessage(content=content))

    return {
        "session_id": str(session_id),
        "message_id": str(message_id),
        "file_ids": [str(row.id) for row in files],
        "messages": messages,
        "iteration": 0,
        "tool_history": [],
        "token_used": 0,
        "pending_approval": None,
        "artifacts": [],
        "finish_reason": None,
        "termination_detail": None,
        "partial_answer": None,
        "model": model,
        "allow_custom_code": allow_custom_code,
        "started_at": now,
        "deadline": now + settings.simple_query_timeout_seconds,
    }


async def _persist_message(
    message_id: uuid.UUID,
    session_id: uuid.UUID,
    answer: str,
    finish_reason: str,
    tool_history: list[dict] | None = None,
) -> None:
    async with SessionLocal() as db:
        message = await db.get(Message, message_id)
        if message is not None:
            message.content = answer
            message.finish_reason = finish_reason[:32]
            if tool_history is not None:
                message.tool_calls_json = tool_history
            await db.commit()
        await session_service.touch_session(
            db, await session_service.get_session(db, session_id)
        )


async def _finalize(
    message_id: uuid.UUID, session_id: uuid.UUID, result: dict
) -> None:
    finish_reason = result.get("finish_reason") or "completed"
    answer = (result.get("partial_answer") or "").strip()
    if not answer:
        answer = "分析已结束，但未生成有效回答。"

    await _persist_message(
        message_id,
        session_id,
        answer,
        finish_reason,
        list(result.get("tool_history") or []),
    )
    async with SessionLocal() as db:
        await memory_service.update_summary(
            db, session_id, answer, list(result.get("tool_history") or [])
        )

    # 先持久化再发终端事件，保证前端收到 done 时数据已可查询
    for chunk in _answer_chunks(answer):
        await sse_bus.publish_event(message_id, "token", {"delta": chunk})
    await sse_bus.set_status(message_id, stage="done", finish_reason=finish_reason)
    await sse_bus.publish_event(
        message_id,
        "done",
        {"message_id": str(message_id), "finish_reason": finish_reason},
    )


async def _fail(
    message_id: uuid.UUID,
    session_id: uuid.UUID,
    code: str,
    error_message: str,
) -> None:
    await _persist_message(
        message_id, session_id, f"分析失败：{error_message}", "failed"
    )
    await sse_bus.set_status(message_id, stage="error", finish_reason="failed")
    await sse_bus.publish_event(
        message_id,
        "error",
        {"code": code, "message": error_message, "retryable": False},
    )


def _track(task: asyncio.Task) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _run_agent(
    *,
    message_id: uuid.UUID,
    session_id: uuid.UUID,
    content: str,
    files: list[File],
    history: list[Message],
    model: str,
    allow_custom_code: bool,
) -> None:
    try:
        graph = get_graph()
        state = _build_state(
            session_id, message_id, content, files, history, model, allow_custom_code
        )
        result = await graph.ainvoke(state, graph_config(str(message_id)))
        if "__interrupt__" in result:
            # 等待用户审批，占位消息保持未完成状态
            return
        await _finalize(message_id, session_id, result)
    except AppError as exc:
        logger.warning("agent failed code=%s", exc.code)
        await _fail(message_id, session_id, exc.code, exc.message)
    except Exception:
        logger.exception("agent crashed")
        await _fail(
            message_id, session_id, "INTERNAL_ERROR", "分析过程中发生内部错误"
        )
    finally:
        await _release_active(session_id)


async def _resume_agent(
    *,
    message_id: uuid.UUID,
    session_id: uuid.UUID,
    approval_id: uuid.UUID,
    decision: str,
) -> None:
    try:
        graph = get_graph()
        result = await graph.ainvoke(
            Command(resume={"decision": decision, "approval_id": str(approval_id)}),
            graph_config(str(message_id)),
        )
        if "__interrupt__" in result:
            return
        await _finalize(message_id, session_id, result)
    except AppError as exc:
        logger.warning("agent resume failed code=%s", exc.code)
        await _fail(message_id, session_id, exc.code, exc.message)
    except Exception:
        logger.exception("agent resume crashed")
        await _fail(
            message_id, session_id, "INTERNAL_ERROR", "恢复执行时发生内部错误"
        )
    finally:
        await _release_active(session_id)


def resume_message(
    *,
    message_id: uuid.UUID,
    session_id: uuid.UUID,
    approval_id: uuid.UUID,
    decision: str,
) -> None:
    _track(
        asyncio.create_task(
            _resume_agent(
                message_id=message_id,
                session_id=session_id,
                approval_id=approval_id,
                decision=decision,
            )
        )
    )


async def mark_stale_messages() -> None:
    """进程重启后清理未完成的占位消息与运行记录；等待审批的记录保留可恢复。"""
    waiting = select(Approval.run_id).where(Approval.status == "pending")
    waiting_messages = select(AnalysisRun.message_id).where(
        AnalysisRun.id.in_(waiting)
    )
    async with SessionLocal() as db:
        await db.execute(
            update(Message)
            .where(
                Message.role == "assistant",
                Message.finish_reason.is_(None),
                Message.id.notin_(waiting_messages),
            )
            .values(finish_reason="failed", content="服务重启，分析已中断，请重新提交问题。")
        )
        await db.execute(
            update(AnalysisRun)
            .where(
                AnalysisRun.status.in_(("pending", "running")),
                AnalysisRun.id.notin_(waiting),
            )
            .values(status="failed", error="服务重启中断", finished_at=func.now())
        )
        await db.commit()


async def wait_background_tasks(timeout: float = 30.0) -> None:
    """测试用：等待当前所有后台 Agent 任务结束。"""
    if _background_tasks:
        await asyncio.wait(set(_background_tasks), timeout=timeout)
