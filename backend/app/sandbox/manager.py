from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import docker
from docker.errors import DockerException, ImageNotFound

from app.config import settings

logger = logging.getLogger("app.sandbox")

MAX_LOG_BYTES = 64 * 1024
SANDBOX_USER = "1000:1000"

_available = False
_reason = "未初始化"


@dataclass
class SandboxResult:
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    artifacts: list[dict[str, object]] = field(default_factory=list)


def is_available() -> bool:
    return _available


def unavailable_reason() -> str:
    return _reason


async def init_sandbox() -> None:
    """启动时 fail-closed 探测：socket、镜像、宿主机路径三者缺一不可。"""
    global _available, _reason
    _available = False

    if not settings.host_data_dir.strip():
        _reason = "HOST_DATA_DIR 未配置"
        logger.warning("sandbox disabled: %s", _reason)
        return
    if not Path("/var/run/docker.sock").exists():
        _reason = "Docker socket 未挂载"
        logger.warning("sandbox disabled: %s", _reason)
        return

    try:
        client = docker.from_env()

        def _probe() -> None:
            client.ping()
            client.images.get(settings.sandbox_image)

        await asyncio.to_thread(_probe)
    except ImageNotFound:
        _reason = f"沙箱镜像不存在: {settings.sandbox_image}"
        logger.warning("sandbox disabled: %s", _reason)
        return
    except (DockerException, OSError) as exc:
        _reason = f"Docker 不可用: {type(exc).__name__}"
        logger.warning("sandbox disabled: %s", _reason)
        return

    _available = True
    _reason = ""
    logger.info("sandbox available image=%s", settings.sandbox_image)


def _to_host_path(container_path: Path) -> str:
    root = Path(settings.data_dir).resolve()
    relative = container_path.resolve().relative_to(root)
    return str(Path(settings.host_data_dir) / relative)


def _collect_artifacts(work_dir: Path, artifact_target: Path) -> list[dict[str, object]]:
    if artifact_target.exists():
        shutil.rmtree(artifact_target, ignore_errors=True)
    artifact_target.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    for item in sorted(work_dir.iterdir()):
        if not item.is_file() or item.name.startswith("snippet") or item.name == "result.json":
            continue
        if item.stat().st_size > 20 * 1024 * 1024:
            continue
        target = artifact_target / item.name
        shutil.copy2(item, target)
        results.append({"name": item.name, "size": item.stat().st_size})
    return results


async def run_snippet(
    code: str,
    work_dir: Path,
    artifact_dir: Path,
    timeout_seconds: int | None = None,
) -> SandboxResult:
    if not _available:
        raise RuntimeError(f"sandbox unavailable: {_reason}")

    timeout = timeout_seconds or settings.sandbox_timeout_seconds
    work_dir.mkdir(parents=True, exist_ok=True)
    work_dir.chmod(0o777)
    snippet_path = work_dir / "snippet.py"
    snippet_path.write_text(code, encoding="utf-8")
    snippet_path.chmod(0o644)

    host_work = _to_host_path(work_dir)
    host_data = settings.host_data_dir
    client = docker.from_env()

    def _start():
        return client.containers.run(
            image=settings.sandbox_image,
            command=["python", "/work/snippet.py"],
            detach=True,
            user=SANDBOX_USER,
            working_dir="/work",
            network_disabled=True,
            mem_limit=settings.sandbox_memory,
            nano_cpus=1_000_000_000,
            pids_limit=128,
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            environment={"MPLBACKEND": "Agg", "HOME": "/tmp", "TZ": settings.analysis_timezone},
            volumes={
                host_data: {"bind": "/data", "mode": "ro"},
                host_work: {"bind": "/work", "mode": "rw"},
            },
            tmpfs={"/tmp": "size=64m"},
            labels={"app": "data-agent-sandbox"},
        )

    started = time.perf_counter()
    container = await asyncio.to_thread(_start)
    timed_out = False
    exit_code: int | None = None

    try:
        wait_result = await asyncio.wait_for(
            asyncio.to_thread(container.wait), timeout=timeout
        )
        exit_code = int(wait_result.get("StatusCode", -1))
    except TimeoutError:
        timed_out = True
        await asyncio.to_thread(container.kill)
    finally:
        raw_logs = await asyncio.to_thread(
            container.logs, stdout=True, stderr=True, tail=200
        )
        await asyncio.to_thread(container.remove, force=True)

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    text = raw_logs.decode("utf-8", "replace")
    if len(text.encode("utf-8")) > MAX_LOG_BYTES:
        text = text.encode("utf-8")[-MAX_LOG_BYTES:].decode("utf-8", "replace")

    artifacts = await asyncio.to_thread(_collect_artifacts, work_dir, artifact_dir)
    status = "timeout" if timed_out else ("success" if exit_code == 0 else "failed")
    return SandboxResult(
        status=status,
        exit_code=exit_code,
        stdout=text if exit_code == 0 else "",
        stderr=text if exit_code != 0 else "",
        duration_ms=duration_ms,
        timed_out=timed_out,
        artifacts=artifacts,
    )
