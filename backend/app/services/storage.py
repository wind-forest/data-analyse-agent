from __future__ import annotations

import uuid
from pathlib import Path

from app.config import settings


def data_root() -> Path:
    return Path(settings.data_dir).resolve()


def sessions_root() -> Path:
    return data_root() / "sessions"


def session_dir(session_id: uuid.UUID | str) -> Path:
    return sessions_root() / str(session_id)


def ensure_session_dirs(session_id: uuid.UUID | str) -> Path:
    directory = session_dir(session_id)
    for name in ("uploads", "work", "artifacts"):
        (directory / name).mkdir(parents=True, exist_ok=True)
    return directory


def work_dir(session_id: uuid.UUID | str, run_id: uuid.UUID | str) -> Path:
    directory = session_dir(session_id) / "work" / str(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def artifact_dir(session_id: uuid.UUID | str, run_id: uuid.UUID | str) -> Path:
    directory = session_dir(session_id) / "artifacts" / str(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def to_relative(path: Path) -> str:
    return path.resolve().relative_to(data_root()).as_posix()


def resolve_relative(relative_path: str) -> Path:
    """将数据库中保存的相对路径还原为绝对路径，并保证不逃逸 data 根目录。"""
    root = data_root()
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("path escapes data root")
    return candidate


def remove_tree(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
