from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from app.agent.llm import LLMResponse, LLMToolCall
from app.config import settings
from app.errors import AppError
from app.sandbox.manager import SandboxResult
from app.sandbox.validator import validate_code


@pytest.fixture(autouse=True)
def agent_env(agent_runtime):
    return agent_runtime


def _finish(answer: str) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[
            LLMToolCall(
                id=f"call-{uuid.uuid4().hex[:6]}",
                name="finish",
                arguments={"answer": answer, "artifact_ids": [], "confidence": 0.9},
            )
        ],
        total_tokens=30,
    )


def _snippet_call(code: str) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[
            LLMToolCall(
                id=f"call-{uuid.uuid4().hex[:6]}",
                name="execute_python_snippet",
                arguments={"code": code, "purpose": "验证沙箱"},
            )
        ],
        total_tokens=40,
    )


def _patch_llm(monkeypatch, responses: list[LLMResponse]) -> None:
    queue = list(responses)

    async def fake(model, messages, tools):
        return queue.pop(0)

    monkeypatch.setattr("app.agent.nodes.chat_completion", fake)


def _patch_sandbox(monkeypatch) -> None:
    async def fake_run(code, work_dir, artifact_dir, timeout_seconds=None):
        return SandboxResult(
            status="success",
            exit_code=0,
            stdout="mean=2.0",
            stderr="",
            duration_ms=12.5,
            artifacts=[{"name": "result.csv", "size": 12}],
        )

    monkeypatch.setattr("app.sandbox.manager.is_available", lambda: True)
    monkeypatch.setattr("app.sandbox.manager.run_snippet", fake_run)


async def _seed(client) -> str:
    session = (await client.post("/api/sessions", json={"title": "审批测试"})).json()
    await client.post(
        "/api/files",
        data={"session_id": session["id"]},
        files={"file": ("data.csv", b"a\n1\n2\n3\n", "text/csv")},
    )
    return session["id"]


async def _submit(client, session_id: str) -> str:
    response = await client.post(
        f"/api/sessions/{session_id}/messages",
        json={"content": "用代码算一下均值", "allow_custom_code": True},
    )
    assert response.status_code == 202, response.text
    return response.json()["message_id"]


async def _events(message_id: str) -> list[dict]:
    from app.services import stream_service

    collected = []
    async for item in stream_service.event_stream(uuid.UUID(message_id), 0):
        collected.append({"event": item.event, "data": json.loads(item.data)})
    return collected


async def _wait() -> None:
    from app.services.agent_service import wait_background_tasks

    await wait_background_tasks(timeout=20)


async def _pending_approval(client, session_id: str, message_id: str) -> str:
    from sqlalchemy import select

    from app.db.models import Approval
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        row = await db.scalar(
            select(Approval)
            .where(Approval.session_id == uuid.UUID(session_id))
            .order_by(Approval.created_at.desc())
            .limit(1)
        )
    assert row is not None, message_id
    return str(row.id)


def test_validator_blocks_dangerous_code() -> None:
    validate_code("import pandas as pd\nprint(pd.DataFrame({'a': [1]}).mean())")

    for code in (
        "import os",
        "import socket",
        "open('x')",
        "eval('1+1')",
        "import pandas as pd\npd.read_csv('/etc/passwd')",
        "class A:\n    def __init__(self): pass\nA().__class__",
        "import subprocess",
    ):
        with pytest.raises(AppError):
            validate_code(code)


async def test_approve_resumes_and_executes(client, monkeypatch) -> None:
    _patch_sandbox(monkeypatch)
    _patch_llm(
        monkeypatch,
        [_snippet_call("import pandas as pd\nprint(2.0)"), _finish("均值为 2.0")],
    )
    session_id = await _seed(client)
    message_id = await _submit(client, session_id)
    await _wait()

    from app.db.models import Message
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        placeholder = await db.get(Message, uuid.UUID(message_id))
        assert placeholder.finish_reason is None
        assert placeholder.content == ""

    approval_id = await _pending_approval(client, session_id, message_id)
    response = await client.post(
        f"/api/approvals/{approval_id}", json={"decision": "approved"}
    )
    assert response.status_code == 202
    await _wait()

    async with SessionLocal() as db:
        message = await db.get(Message, uuid.UUID(message_id))
        assert message.finish_reason == "completed"
        assert message.content == "均值为 2.0"

    events = await _events(message_id)
    required = [item for item in events if item["event"] == "approval_required"]
    calls = [item for item in events if item["event"] == "tool_call"]
    results = [item for item in events if item["event"] == "tool_result"]
    assert len(required) == 1
    assert required[0]["data"]["tool"] == "execute_python_snippet"
    assert calls and results
    assert calls[0]["data"]["run_id"] == results[0]["data"]["run_id"]
    assert results[0]["data"]["status"] == "success"
    assert events[-1]["event"] == "done"


async def test_reject_returns_observation_and_finishes(client, monkeypatch) -> None:
    _patch_sandbox(monkeypatch)
    _patch_llm(
        monkeypatch,
        [_snippet_call("print(1)"), _finish("已取消该操作，改用内置工具分析")],
    )
    session_id = await _seed(client)
    message_id = await _submit(client, session_id)
    await _wait()

    approval_id = await _pending_approval(client, session_id, message_id)
    response = await client.post(
        f"/api/approvals/{approval_id}", json={"decision": "rejected"}
    )
    assert response.status_code == 202
    await _wait()

    from app.db.models import AnalysisRun, Message
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        message = await db.get(Message, uuid.UUID(message_id))
        assert message.finish_reason == "completed"
        run = await db.get(AnalysisRun, await _run_id_for(approval_id))
        assert run.status == "failed"

    events = await _events(message_id)
    assert not any(item["event"] == "tool_result" for item in events)
    assert events[-1]["event"] == "done"


async def _run_id_for(approval_id: str) -> uuid.UUID:
    from app.db.models import Approval
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        row = await db.get(Approval, uuid.UUID(approval_id))
        assert row is not None
        return row.run_id


async def test_second_decision_conflicts(client, monkeypatch) -> None:
    _patch_sandbox(monkeypatch)
    _patch_llm(
        monkeypatch,
        [_snippet_call("print(1)"), _finish("完成")],
    )
    session_id = await _seed(client)
    message_id = await _submit(client, session_id)
    await _wait()

    approval_id = await _pending_approval(client, session_id, message_id)
    first = await client.post(
        f"/api/approvals/{approval_id}", json={"decision": "approved"}
    )
    assert first.status_code == 202
    second = await client.post(
        f"/api/approvals/{approval_id}", json={"decision": "approved"}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "APPROVAL_NOT_PENDING"
    await _wait()


async def test_expired_approval_closes_message(client, monkeypatch) -> None:
    from app.services import approval_service

    _patch_sandbox(monkeypatch)
    _patch_llm(monkeypatch, [_snippet_call("print(1)")])
    session_id = await _seed(client)
    message_id = await _submit(client, session_id)
    await _wait()

    from sqlalchemy import update

    from app.db.models import Approval
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        await db.execute(
            update(Approval)
            .where(Approval.session_id == uuid.UUID(session_id))
            .values(created_at=datetime.now(UTC) - timedelta(seconds=600))
        )
        await db.commit()

    monkeypatch.setattr(settings, "approval_timeout_seconds", 300)
    expired = await approval_service.sweep_expired()
    assert expired == 1

    from app.db.models import Message

    async with SessionLocal() as db:
        message = await db.get(Message, uuid.UUID(message_id))
        assert message.finish_reason == "timeout"
        approval = await db.get(Approval, uuid.UUID(await _pending_approval(client, session_id, message_id)))
        assert approval.status == "rejected"
        assert approval.resolution_reason == "timeout"

    events = await _events(message_id)
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["finish_reason"] == "timeout"


async def test_memory_tool_and_session_summary(client, monkeypatch) -> None:
    from app.services import run_service
    from app.tools import registry
    from app.tools.base import ToolDefinition, ToolResult

    class FakeArgs(BaseModel):
        label: str = "x"

    async def fake_handler(args, ctx):
        run = await run_service.start_run(
            ctx.db, ctx.session_id, "fake_memory_tool", args.model_dump()
        )
        return ToolResult(run_id=run.id, summary=f"统计 {args.label} 完成")

    monkeypatch.setitem(
        registry.TOOLS,
        "fake_memory_tool",
        ToolDefinition(
            name="fake_memory_tool", description="记忆测试", args_model=FakeArgs, handler=fake_handler
        ),
    )
    _patch_llm(
        monkeypatch,
        [
            LLMResponse(
                content="",
                tool_calls=[
                    LLMToolCall(
                        id="call-mem", name="fake_memory_tool", arguments={"label": "销量"}
                    )
                ],
            ),
            _finish("销量统计划算完成，详见步骤记录。"),
        ],
    )

    session_id = await _seed(client)
    await _submit(client, session_id)
    await _wait()

    response = await client.post(
        "/api/tools/memory",
        json={"session_id": session_id, "query": "销量", "top_k": 5},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["session_summary"]
    assert any("销量" in item["summary"] for item in body["data"]["matches"])