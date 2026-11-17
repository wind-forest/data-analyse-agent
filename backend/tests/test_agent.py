from __future__ import annotations

import uuid

import pytest

from app.agent.llm import LLMResponse, LLMToolCall
from app.config import settings


@pytest.fixture(autouse=True)
def agent_env(agent_runtime):
    return agent_runtime


def _finish(answer: str, artifact_ids: list[str] | None = None) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[
            LLMToolCall(
                id=f"call-{uuid.uuid4().hex[:6]}",
                name="finish",
                arguments={
                    "answer": answer,
                    "artifact_ids": artifact_ids or [],
                    "confidence": 0.8,
                },
            )
        ],
        total_tokens=120,
    )


def _tool_call(name: str, arguments: dict, call_id: str | None = None) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[
            LLMToolCall(
                id=call_id or f"call-{uuid.uuid4().hex[:6]}",
                name=name,
                arguments=arguments,
            )
        ],
        total_tokens=80,
    )


def _patch_llm(monkeypatch, responses: list[LLMResponse]) -> None:
    queue = list(responses)

    async def fake(model, messages, tools):
        if not queue:
            raise AssertionError("LLM 调用次数超出预期")
        return queue.pop(0)

    monkeypatch.setattr("app.agent.nodes.chat_completion", fake)


async def _seed_session(client, upload: bool = True) -> dict[str, str]:
    session = (await client.post("/api/sessions", json={"title": "Agent 测试"})).json()
    file_id = ""
    if upload:
        response = await client.post(
            "/api/files",
            data={"session_id": session["id"]},
            files={"file": ("data.csv", b"a,b\n1,2\n3,4\n", "text/csv")},
        )
        file_id = response.json()["id"]
    return {"session_id": session["id"], "file_id": file_id}


async def _submit(client, session_id: str, content: str = "分析一下") -> dict:
    response = await client.post(
        f"/api/sessions/{session_id}/messages", json={"content": content}
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _read_assistant(client, session_id: str, message_id: str) -> dict:
    from app.services.agent_service import wait_background_tasks

    await wait_background_tasks(timeout=20)
    messages = (await client.get(f"/api/sessions/{session_id}/messages")).json()
    target = next(item for item in messages if item["id"] == message_id)
    return target


async def test_finish_completes_and_persists(client, monkeypatch) -> None:
    seeded = await _seed_session(client)
    _patch_llm(monkeypatch, [_finish("数据共 2 行，字段为 a 和 b。")])

    submitted = await _submit(client, seeded["session_id"])
    assistant = await _read_assistant(
        client, seeded["session_id"], submitted["message_id"]
    )

    assert assistant["role"] == "assistant"
    assert assistant["finish_reason"] == "completed"
    assert "2 行" in assistant["content"]

    messages = (await client.get(f"/api/sessions/{seeded['session_id']}/messages")).json()
    assert [item["role"] for item in messages] == ["user", "assistant"]


async def test_direct_text_is_nudged_to_finish(client, monkeypatch) -> None:
    seeded = await _seed_session(client)
    _patch_llm(
        monkeypatch,
        [LLMResponse(content="我认为是 42", total_tokens=50), _finish("正式结论")],
    )

    submitted = await _submit(client, seeded["session_id"])
    assistant = await _read_assistant(
        client, seeded["session_id"], submitted["message_id"]
    )

    assert assistant["finish_reason"] == "completed"
    assert assistant["content"] == "正式结论"


async def test_tool_error_becomes_observation(client, monkeypatch) -> None:
    seeded = await _seed_session(client)
    missing = str(uuid.uuid4())
    _patch_llm(
        monkeypatch,
        [
            _tool_call("evaluate_model", {"model_id": missing}),
            _finish("没有找到模型，无法评估。"),
        ],
    )

    submitted = await _submit(client, seeded["session_id"])
    assistant = await _read_assistant(
        client, seeded["session_id"], submitted["message_id"]
    )

    assert assistant["finish_reason"] == "completed"
    assert "没有找到模型" in assistant["content"]


async def test_tool_history_is_persisted_for_restore(client, monkeypatch) -> None:
    from app.tools.base import ToolResult

    seeded = await _seed_session(client)
    run_id = uuid.uuid4()

    async def fake_execute(name, arguments, context):
        return ToolResult(run_id=run_id, summary="历史查询完成")

    monkeypatch.setattr("app.agent.nodes.execute_tool", fake_execute)
    _patch_llm(
        monkeypatch,
        [
            _tool_call("query_session_memory", {}, call_id="history-call"),
            _finish("已查询历史。"),
        ],
    )

    submitted = await _submit(client, seeded["session_id"])
    assistant = await _read_assistant(
        client, seeded["session_id"], submitted["message_id"]
    )

    assert assistant["tool_calls_json"] == [
        {
            "tool": "query_session_memory",
            "params": {},
            "hash": assistant["tool_calls_json"][0]["hash"],
            "summary": "历史查询完成",
            "call_id": "history-call",
            "run_id": str(run_id),
            "status": "success",
            "duration_ms": assistant["tool_calls_json"][0]["duration_ms"],
            "error": None,
            "artifact_ids": [],
        }
    ]
    assert assistant["tool_calls_json"][0]["duration_ms"] >= 0


async def test_duplicate_tool_call_terminates(client, monkeypatch) -> None:
    seeded = await _seed_session(client)
    missing = str(uuid.uuid4())
    duplicated = _tool_call("evaluate_model", {"model_id": missing}, call_id="dup-1")
    _patch_llm(monkeypatch, [duplicated, cloned_duplicate(duplicated), _finish("不应到达")])

    submitted = await _submit(client, seeded["session_id"])
    assistant = await _read_assistant(
        client, seeded["session_id"], submitted["message_id"]
    )

    assert assistant["finish_reason"] == "max_iterations"
    assert "分析未完全结束" in assistant["content"]


def cloned_duplicate(response: LLMResponse) -> LLMResponse:
    call = response.tool_calls[0]
    return LLMResponse(
        content="",
        tool_calls=[
            LLMToolCall(id="dup-2", name=call.name, arguments=dict(call.arguments))
        ],
        total_tokens=80,
    )


async def test_max_iterations_path(client, monkeypatch) -> None:
    seeded = await _seed_session(client)
    monkeypatch.setattr(settings, "max_iterations", 2)
    _patch_llm(
        monkeypatch,
        [
            LLMResponse(content="先看看数据", total_tokens=10),
            LLMResponse(content="还没有结论", total_tokens=10),
            _finish("不应到达"),
        ],
    )

    submitted = await _submit(client, seeded["session_id"])
    assistant = await _read_assistant(
        client, seeded["session_id"], submitted["message_id"]
    )

    assert assistant["finish_reason"] == "max_iterations"
    assert "达到最大迭代次数" in assistant["content"]


async def test_token_budget_path(client, monkeypatch) -> None:
    seeded = await _seed_session(client)
    monkeypatch.setattr(settings, "agent_token_budget", 100)
    _patch_llm(
        monkeypatch,
        [LLMResponse(content="消耗预算", total_tokens=500), _finish("不应到达")],
    )

    submitted = await _submit(client, seeded["session_id"])
    assistant = await _read_assistant(
        client, seeded["session_id"], submitted["message_id"]
    )

    assert assistant["finish_reason"] == "budget_exceeded"
    assert "token 预算" in assistant["content"]


async def test_llm_auth_error_marks_failed(client, monkeypatch) -> None:
    from app.errors import AppError

    seeded = await _seed_session(client)

    async def failing(model, messages, tools):
        raise AppError("LLM_AUTH_ERROR", "模型服务鉴权失败", 502)

    monkeypatch.setattr("app.agent.nodes.chat_completion", failing)

    submitted = await _submit(client, seeded["session_id"])
    assistant = await _read_assistant(
        client, seeded["session_id"], submitted["message_id"]
    )

    assert assistant["finish_reason"] == "failed"
    assert "鉴权失败" in assistant["content"]


async def test_message_running_guard(client) -> None:
    from app.db.redis import get_redis

    seeded = await _seed_session(client)
    redis = get_redis()
    key = f"session:{seeded['session_id']}:active"
    await redis.set(key, "1", ex=60)
    try:
        response = await client.post(
            f"/api/sessions/{seeded['session_id']}/messages",
            json={"content": "再来一次"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "MESSAGE_RUNNING"
    finally:
        await redis.delete(key)


async def test_mark_stale_messages_on_restart(client) -> None:
    from app.db.models import AnalysisRun, Message
    from app.db.session import SessionLocal
    from app.services.agent_service import mark_stale_messages

    seeded = await _seed_session(client)
    session_id = uuid.UUID(seeded["session_id"])
    async with SessionLocal() as db:
        run = AnalysisRun(
            session_id=session_id, tool_name="profile_dataset", status="running"
        )
        placeholder = Message(session_id=session_id, role="assistant", content="")
        db.add_all([run, placeholder])
        await db.commit()
        run_id, message_id = run.id, placeholder.id

    await mark_stale_messages()

    async with SessionLocal() as db:
        stale_message = await db.get(Message, message_id)
        stale_run = await db.get(AnalysisRun, run_id)
        assert stale_message.finish_reason == "failed"
        assert "服务重启" in stale_message.content
        assert stale_run.status == "failed"


async def test_validation_paths(client) -> None:
    empty_session = await _seed_session(client, upload=False)
    no_file = await client.post(
        f"/api/sessions/{empty_session['session_id']}/messages",
        json={"content": "分析一下"},
    )
    assert no_file.status_code == 400
    assert no_file.json()["error"]["code"] == "FILE_REQUIRED"

    seeded = await _seed_session(client)
    bad_model = await client.post(
        f"/api/sessions/{seeded['session_id']}/messages",
        json={"content": "分析一下", "model": "gpt-4o"},
    )
    assert bad_model.status_code == 400
    assert bad_model.json()["error"]["code"] == "MODEL_NOT_ALLOWED"

    blank = await client.post(
        f"/api/sessions/{seeded['session_id']}/messages", json={"content": "   "}
    )
    assert blank.status_code == 422
