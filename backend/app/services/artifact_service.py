from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisRun, Artifact
from app.errors import AppError


async def create_artifact(
    db: AsyncSession,
    run_id: uuid.UUID,
    artifact_type: str,
    payload: dict[str, Any] | None = None,
    file_path: str | None = None,
) -> Artifact:
    artifact = Artifact(
        run_id=run_id,
        type=artifact_type,
        payload_json=payload,
        file_path=file_path,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def get_artifact(db: AsyncSession, artifact_id: uuid.UUID) -> Artifact:
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise AppError("ARTIFACT_NOT_FOUND", "产物不存在", 404)
    return artifact


async def get_session_artifact(
    db: AsyncSession, session_id: uuid.UUID, artifact_id: uuid.UUID
) -> Artifact:
    artifact = await get_artifact(db, artifact_id)
    run = await db.get(AnalysisRun, artifact.run_id)
    if run is None or run.session_id != session_id:
        raise AppError("ARTIFACT_NOT_FOUND", "产物不存在", 404)
    return artifact
