from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import File
from app.errors import AppError
from app.services import file_service
from app.services.dataset_schema import DatasetSpec, detect_dataset
from app.services.storage import resolve_relative


@dataclass
class ResolvedDataset:
    file: File
    spec: DatasetSpec
    path: Path


async def resolve_dataset(
    db: AsyncSession, session_id: uuid.UUID, file_id: uuid.UUID
) -> ResolvedDataset:
    row = await file_service.get_file(db, session_id, file_id)
    if row.status != "ready":
        raise AppError("FILE_NOT_READY", "文件尚未就绪，无法分析", 409)

    try:
        path = resolve_relative(row.stored_path)
    except ValueError as exc:
        raise AppError("FILE_NOT_FOUND", "文件路径无效", 404) from exc

    if not path.exists():
        raise AppError("FILE_NOT_FOUND", "文件已不存在", 404)

    try:
        spec = detect_dataset(path)
    except ValueError as exc:
        raise AppError("INVALID_FILE", str(exc), 400) from exc

    return ResolvedDataset(file=row, spec=spec, path=path)


async def find_songs_dataset(
    db: AsyncSession, session_id: uuid.UUID
) -> ResolvedDataset | None:
    rows = await db.scalars(
        select(File).where(File.session_id == session_id, File.status == "ready")
    )
    for row in rows:
        try:
            path = resolve_relative(row.stored_path)
            spec = detect_dataset(path)
        except (ValueError, OSError):
            continue
        if spec.kind == "songs":
            return ResolvedDataset(file=row, spec=spec, path=path)
    return None
