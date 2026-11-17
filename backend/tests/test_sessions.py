from __future__ import annotations

from httpx import AsyncClient


async def test_create_and_list_sessions(client: AsyncClient) -> None:
    created = await client.post("/api/sessions", json={"title": "销量分析"})
    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "销量分析"
    assert body["summary"] is None

    listed = await client.get("/api/sessions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]


async def test_default_title(client: AsyncClient) -> None:
    created = await client.post("/api/sessions", json={})
    assert created.status_code == 201
    assert created.json()["title"] == "新分析"


async def test_get_missing_session(client: AsyncClient) -> None:
    response = await client.get("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


async def test_delete_session_and_children(client: AsyncClient) -> None:
    session = (await client.post("/api/sessions", json={})).json()
    session_id = session["id"]

    uploaded = await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert uploaded.status_code == 201

    deleted = await client.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/sessions/{session_id}")).status_code == 404

    files = await client.get("/api/files", params={"session_id": session_id})
    assert files.status_code == 404


async def test_messages_and_artifacts_empty(client: AsyncClient) -> None:
    session = (await client.post("/api/sessions", json={})).json()
    session_id = session["id"]

    messages = await client.get(f"/api/sessions/{session_id}/messages")
    assert messages.status_code == 200
    assert messages.json() == []

    artifacts = await client.get(f"/api/sessions/{session_id}/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json() == []


async def test_artifact_includes_message_id_from_run_context(client, db_session) -> None:
    import uuid

    from app.db.models import Artifact, Message
    from app.services import run_service, sse_bus

    session = (await client.post("/api/sessions", json={})).json()
    session_id = uuid.UUID(session["id"])
    message = Message(session_id=session_id, role="assistant", content="分析结果")
    db_session.add(message)
    await db_session.commit()

    with sse_bus.bind_event_context(message.id, "artifact-call"):
        run = await run_service.start_run(
            db_session, session_id, "profile_dataset", {}
        )
    artifact = Artifact(run_id=run.id, type="table", payload_json={"rows": []})
    db_session.add(artifact)
    await db_session.commit()

    assert run.message_id == message.id
    response = await client.get(f"/api/sessions/{session_id}/artifacts")
    assert response.status_code == 200
    assert response.json()[0]["message_id"] == str(message.id)


async def test_submit_message_requires_llm_key(client, monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "")
    session = (await client.post("/api/sessions", json={})).json()
    response = await client.post(
        f"/api/sessions/{session['id']}/messages", json={"content": "分析一下"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
