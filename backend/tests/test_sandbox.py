from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import settings
from app.sandbox import manager
from app.services import storage

pytestmark = pytest.mark.slow

# conftest 把 DATA_DIR 指向容器内临时目录，宿主机无法挂载；沙箱用例改用真正的 /data
HOST_VISIBLE_DATA_DIR = "/data"


@pytest.fixture(scope="module", autouse=True)
async def sandbox_ready() -> None:
    await manager.init_sandbox()
    if not manager.is_available():
        pytest.skip(manager.unavailable_reason())


@pytest.fixture
def mapped_dirs(monkeypatch) -> Iterator[tuple[Path, Path]]:
    monkeypatch.setattr(settings, "data_dir", HOST_VISIBLE_DATA_DIR)
    session_id = uuid.uuid4()
    run_id = uuid.uuid4()
    work = storage.work_dir(session_id, run_id) / "sandbox"
    work.mkdir(parents=True, exist_ok=True)
    artifacts = storage.artifact_dir(session_id, run_id) / "sandbox"
    try:
        yield work, artifacts
    finally:
        storage.remove_tree(storage.session_dir(session_id))


async def test_success_executes_and_collects_artifacts(mapped_dirs) -> None:
    work, artifacts = mapped_dirs
    code = (
        "import pandas as pd\n"
        "frame = pd.DataFrame({'a': [1, 2, 3]})\n"
        "print(frame['a'].mean())\n"
        "frame.to_csv('result.csv', index=False)\n"
    )
    result = await manager.run_snippet(code, work, artifacts, timeout_seconds=60)

    assert result.status == "success"
    assert result.exit_code == 0
    assert "2.0" in result.stdout
    assert any(item["name"] == "result.csv" for item in result.artifacts)
    assert (artifacts / "result.csv").exists()


async def test_runs_as_non_root_and_data_is_read_only(mapped_dirs) -> None:
    work, artifacts = mapped_dirs
    code = (
        "import os\n"
        "print('uid', os.getuid())\n"
        "try:\n"
        "    open('/data/should_fail.txt', 'w').write('x')\n"
        "except OSError as exc:\n"
        "    print('write denied', type(exc).__name__)\n"
    )
    result = await manager.run_snippet(code, work, artifacts, timeout_seconds=60)

    assert result.status == "success"
    assert "uid 1000" in result.stdout
    assert "write denied" in result.stdout


async def test_network_is_disabled(mapped_dirs) -> None:
    work, artifacts = mapped_dirs
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
        "    print('connected')\n"
        "except OSError as exc:\n"
        "    print('network blocked', type(exc).__name__)\n"
    )
    result = await manager.run_snippet(code, work, artifacts, timeout_seconds=60)

    assert "network blocked" in result.stdout
    assert "connected" not in result.stdout


async def test_timeout_kills_container(mapped_dirs) -> None:
    work, artifacts = mapped_dirs
    result = await manager.run_snippet(
        "import time\ntime.sleep(10)\n", work, artifacts, timeout_seconds=1
    )

    assert result.status == "timeout"
    assert result.timed_out is True
