from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AnalysisRun, File
from app.errors import AppError
from app.services import session_service
from app.services.storage import (
    remove_tree,
    resolve_relative,
    sessions_root,
    to_relative,
)

CHUNK_SIZE = 8 * 1024 * 1024
HEAD_SIZE = 8192

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".json": "application/json",
}

ACTIVE_RUN_STATUSES = ("pending", "running", "waiting_approval")


def _max_size_bytes() -> int:
    return settings.max_upload_size_mb * 1024 * 1024


def _safe_name(raw_name: str | None) -> str:
    cleaned = (raw_name or "").replace("\\", "/")
    name = Path(cleaned).name
    if not name or name in {".", ".."} or "\x00" in name:
        raise AppError("INVALID_FILE", "文件名无效", 400)
    return name


def _validate_content(extension: str, head: bytes) -> None:
    if b"\x00" in head:
        raise AppError("INVALID_FILE", "文件内容包含二进制数据，无法作为文本表格读取", 400)

    if extension == ".xlsx":
        if not head.startswith(b"PK\x03\x04"):
            raise AppError("INVALID_FILE", "xlsx 文件签名不合法", 400)
        return

    if extension == ".json":
        stripped = head.lstrip()
        if not stripped.startswith((b"{", b"[")):
            raise AppError("INVALID_FILE", "json 文件内容不是对象或数组", 400)
        return

    sample = head[:-4] if len(head) > 4 else head
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            sample.decode(encoding)
            return
        except UnicodeDecodeError:
            continue
    raise AppError("INVALID_FILE", "无法以 UTF-8 或 GB18030 解码文本文件", 400)


async def save_upload(
    db: AsyncSession, session_id: uuid.UUID, upload: UploadFile
) -> File:
    session = await session_service.get_session(db, session_id)
    original_name = _safe_name(upload.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        supported = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise AppError("INVALID_FILE", f"不支持的文件类型，仅支持 {supported}", 400)

    file_id = uuid.uuid4()
    target_dir = sessions_root() / str(session_id) / "uploads" / str(file_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    temp_path = target_dir / ".uploading"
    final_path = target_dir / original_name

    limit = _max_size_bytes()
    hasher = hashlib.sha256()
    size = 0
    head = b""

    try:
        with temp_path.open("wb") as output:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise AppError(
                        "FILE_TOO_LARGE",
                        f"文件超过 {settings.max_upload_size_mb} MB 上限",
                        413,
                    )
                if len(head) < HEAD_SIZE:
                    head += chunk[: HEAD_SIZE - len(head)]
                hasher.update(chunk)
                output.write(chunk)

        if size == 0:
            raise AppError("INVALID_FILE", "文件为空", 400)

        _validate_content(extension, head)
        temp_path.replace(final_path)
    except BaseException:
        remove_tree(target_dir)
        raise
    finally:
        await upload.close()

    row = File(
        id=file_id,
        session_id=session_id,
        original_name=original_name,
        stored_path=to_relative(final_path),
        sha256=hasher.hexdigest(),
        mime=ALLOWED_EXTENSIONS[extension],
        size=size,
        status="ready",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await session_service.touch_session(db, session)
    return row


async def list_files(db: AsyncSession, session_id: uuid.UUID) -> list[File]:
    await session_service.get_session(db, session_id)
    result = await db.scalars(
        select(File)
        .where(File.session_id == session_id)
        .order_by(File.created_at.desc())
    )
    return list(result)


async def get_file(
    db: AsyncSession, session_id: uuid.UUID, file_id: uuid.UUID
) -> File:
    row = await db.get(File, file_id)
    if row is None or row.session_id != session_id:
        raise AppError("FILE_NOT_FOUND", "文件不存在", 404)
    return row


async def delete_file(
    db: AsyncSession, session_id: uuid.UUID, file_id: uuid.UUID
) -> None:
    row = await get_file(db, session_id, file_id)

    active_runs = await db.scalar(
        select(func.count())
        .select_from(AnalysisRun)
        .where(
            AnalysisRun.file_id == file_id,
            AnalysisRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    )
    if active_runs:
        raise AppError("FILE_IN_USE", "文件正在被分析任务使用，无法删除", 409)

    try:
        stored = resolve_relative(row.stored_path)
    except ValueError:
        stored = None

    await db.delete(row)
    await db.commit()

    if stored is not None:
        remove_tree(stored.parent.parent)
