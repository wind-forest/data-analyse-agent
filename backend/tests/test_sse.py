from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest
from pydantic import BaseModel

from app.agent.llm import LLMResponse, LLMToolCall


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
        total_tokens=50,
    )


def _tool_call(name: str, arguments: dict) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[
            LLMToolCall(
                id=f"call-{uuid.uuid4().hex[:6]}", name=name, arguments=arguments
            )
        ],
        total_tokens=40,
    )


def _patch_llm(monkeypatch, responses: list[LLMResponse]) -> None:
    queue = list(responses)

    async def fake(model, messages, tools):
        return queue.pop(0)

    monkeypatch.setattr("app.agent.nodes.chat_completion", fake)


async def _seed(client) -> str:
    session = (await client.post("/api/sessions", json={"title": "SSE 测试"})).json()
    await client.post(
        "/api/files",
        data={"session_id": session["id"]},
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    return session["id"]


async def _submit(client, session_id: str) -> str:
    response = await client.post(
        f"/api/sessions/{session_id}/messages", json={"content": "分析数据"}
    )
    assert response.status_code == 202, response.text
    return response.json()["message_id"]


async def _collect(message_id: str, resume_id: int = 0) -> list[dict[str, Any]]:
    from app.services import stream_service

    events: list[dict[str, Any]] = []

    async def run() -> None:
        async for item in stream_service.event_stream(
            uuid.UUID(message_id), resume_id
        ):
            events.append(
                {
                    "event": item.event,
                    "id": int(item.id) if item.id else None,
                    "data": json.loads(item.data),
                }
            )

    await asyncio.wait_for(run(), timeout=15)
    return events


async def _wait_agent() -> None:
    from app.services.agent_service import wait_background_tasks

    await wait_background_tasks(timeout=20)


async def test_stream_replays_full_sequence(client, monkeypatch) -> None:
    session_id = await _seed(client)
    _patch_llm(monkeypatch, [_finish("数据只有两行。")])
    message_id = await _submit(client, session_id)
    await _wait_agent()

    events = await _collect(message_id)

    names = [item["event"] for item in events]
    stages = [
        item["data"].get("stage") for item in events if item["event"] == "status"
    ]
    assert names[0] == "status"
    assert events[0]["data"]["stage"] == "queued"
    assert "thinking" in stages
    assert "finishing" in stages
    assert "token" in names
    assert names[-1] == "done"
    assert events[-1]["data"]["finish_reason"] == "completed"

    ids = [item["id"] for item in events]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)

    answer = "".join(
        item["data"]["delta"] for item in events if item["event"] == "token"
    )
    assert answer == "数据只有两行。"


async def test_stream_resume_skips_delivered_events(client, monkeypatch) -> None:
    session_id = await _seed(client)
    _patch_llm(monkeypatch, [_finish("复述完成。")])
    message_id = await _submit(client, session_id)
    await _wait_agent()

    full = await _collect(message_id)
    resume_after = full[2]["id"]

    resumed = await _collect(message_id, resume_id=resume_after)

    assert resumed
    assert all(item["id"] > resume_after for item in resumed)
    assert resumed[-1]["event"] == "done"


async def test_stream_gap_when_cache_expired(client, monkeypatch) -> None:
    from app.db.redis import get_redis

    session_id = await _seed(client)
    _patch_llm(monkeypatch, [_finish("缓存测试。")])
    message_id = await _submit(client, session_id)
    await _wait_agent()

    redis = get_redis()
    await redis.delete(f"message:{message_id}:events")
    await redis.set(f"message:{message_id}:event_seq", 99)

    events = await _collect(message_id, resume_id=10)

    assert len(events) == 1
    assert events[0]["event"] == "error"
    assert events[0]["data"]["code"] == "EVENT_GAP"


async def test_stream_closes_when_already_complete(client, monkeypatch) -> None:
    from app.db.redis import get_redis

    session_id = await _seed(client)
    _patch_llm(monkeypatch, [_finish("已完成。")])
    message_id = await _submit(client, session_id)
    await _wait_agent()

    sequence = int(await get_redis().get(f"message:{message_id}:event_seq") or 0)
    events = await _collect(message_id, resume_id=sequence)
    assert events == []


async def test_stream_unknown_message_returns_404(client) -> None:
    session_id = await _seed(client)
    response = await client.get(
        f"/api/sessions/{session_id}/stream?message_id={uuid.uuid4()}"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MESSAGE_NOT_FOUND"


async def test_tool_events_share_call_and_run_id(client, monkeypatch) -> None:
    from app.services import run_service
    from app.tools import registry
    from app.tools.base import ToolDefinition, ToolResult

    class FakeArgs(BaseModel):
        label: str = "demo"

    async def fake_handler(args, ctx):
        run = await run_service.start_run(
            ctx.db,
            ctx.session_id,
            "fake_tool",
            args.model_dump(),
            file_id=None,
            message_id=ctx.message_id,
        )
        return ToolResult(run_id=run.id, summary="fake ok", artifact_ids=[])

    monkeypatch.setitem(
        registry.TOOLS,
        "fake_tool",
        ToolDefinition(
            name="fake_tool",
            description="测试用工具",
            args_model=FakeArgs,
            handler=fake_handler,
        ),
    )

    session_id = await _seed(client)
    _patch_llm(
        monkeypatch, [_tool_call("fake_tool", {"label": "demo"}), _finish("工具完成")]
    )
    message_id = await _submit(client, session_id)
    await _wait_agent()

    events = await _collect(message_id)
    calls = [item for item in events if item["event"] == "tool_call"]
    results = [item for item in events if item["event"] == "tool_result"]

    assert len(calls) == 1 and len(results) == 1
    assert calls[0]["data"]["tool"] == "fake_tool"
    assert calls[0]["data"]["run_id"] == results[0]["data"]["run_id"]
    assert calls[0]["data"]["call_id"] == results[0]["data"]["call_id"]
    assert results[0]["data"]["status"] == "success"
    assert calls[0]["id"] < results[0]["id"]


async def test_stream_emits_error_terminal_only(client, monkeypatch) -> None:
    from app.errors import AppError

    session_id = await _seed(client)

    async def failing(model, messages, tools):
        raise AppError("LLM_AUTH_ERROR", "鉴权失败", 502)

    monkeypatch.setattr("app.agent.nodes.chat_completion", failing)
    message_id = await _submit(client, session_id)
    await _wait_agent()

    events = await _collect(message_id)
    names = [item["event"] for item in events]

    assert names[-1] == "error"
    assert "done" not in names
    assert events[-1]["data"]["code"] == "LLM_AUTH_ERROR"
