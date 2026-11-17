from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from app.config import settings


async def _create_session(client: AsyncClient) -> str:
    response = await client.post("/api/sessions", json={})
    return response.json()["id"]


async def test_upload_headerless_csv(client: AsyncClient) -> None:
    session_id = await _create_session(client)
    content = b"u1,s1,1426406400,1,20150315\nu2,s1,1426417200,3,20150315\n"

    response = await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("actions.csv", content, "text/csv")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ready"
    assert body["size"] == len(content)
    assert len(body["sha256"]) == 64
    assert body["original_name"] == "actions.csv"

    stored = (
        Path(settings.data_dir) / "sessions" / session_id / "uploads" / body["id"]
        / "actions.csv"
    )
    assert stored.exists()
    assert stored.read_bytes() == content

    listed = await client.get("/api/files", params={"session_id": session_id})
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_reject_unsupported_extension(client: AsyncClient) -> None:
    session_id = await _create_session(client)
    response = await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILE"


async def test_reject_empty_and_binary_csv(client: AsyncClient) -> None:
    session_id = await _create_session(client)

    empty = await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert empty.status_code == 400

    binary = await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("binary.csv", b"A\x00B", "text/csv")},
    )
    assert binary.status_code == 400


async def test_upload_path_traversal_filename_is_sanitized(client: AsyncClient) -> None:
    session_id = await _create_session(client)
    response = await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("../../evil.csv", b"a,b\n1,2\n", "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["original_name"] == "evil.csv"

    session_root = Path(settings.data_dir) / "sessions" / session_id
    for path in session_root.rglob("evil.csv"):
        assert path.is_relative_to(session_root)


async def test_cross_session_access_denied(client: AsyncClient) -> None:
    owner = await _create_session(client)
    other = await _create_session(client)
    uploaded = await client.post(
        "/api/files",
        data={"session_id": owner},
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    file_id = uploaded.json()["id"]

    response = await client.delete(
        f"/api/files/{file_id}", params={"session_id": other}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_FOUND"


async def test_delete_file_removes_directory(client: AsyncClient) -> None:
    session_id = await _create_session(client)
    uploaded = (
        await client.post(
            "/api/files",
            data={"session_id": session_id},
            files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
        )
    ).json()

    response = await client.delete(
        f"/api/files/{uploaded['id']}", params={"session_id": session_id}
    )
    assert response.status_code == 204

    upload_dir = (
        Path(settings.data_dir)
        / "sessions"
        / session_id
        / "uploads"
        / uploaded["id"]
    )
    assert not upload_dir.exists()

    listed = await client.get("/api/files", params={"session_id": session_id})
    assert listed.json() == []


async def test_session_delete_removes_files_from_disk(client: AsyncClient) -> None:
    session_id = await _create_session(client)
    await client.post(
        "/api/files",
        data={"session_id": session_id},
        files={"file": ("data.csv", b"a,b\n1,2\n", "text/csv")},
    )
    session_root = Path(settings.data_dir) / "sessions" / session_id
    assert session_root.exists()

    assert (await client.delete(f"/api/sessions/{session_id}")).status_code == 204
    assert not session_root.exists()


async def test_config_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["default_model"] == settings.model_name
    assert body["max_upload_size_mb"] == settings.max_upload_size_mb
    assert body["custom_code_available"] is False
