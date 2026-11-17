from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.dependencies import SessionDep
from app.schemas.files import FileRead
from app.services import file_service

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FileRead, status_code=201)
async def upload_file(
    db: SessionDep,
    session_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> FileRead:
    row = await file_service.save_upload(db, session_id, file)
    return FileRead.model_validate(row)


@router.get("", response_model=list[FileRead])
async def list_files(
    db: SessionDep,
    session_id: Annotated[uuid.UUID, Query()],
) -> list[FileRead]:
    rows = await file_service.list_files(db, session_id)
    return [FileRead.model_validate(row) for row in rows]


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    db: SessionDep,
    file_id: uuid.UUID,
    session_id: Annotated[uuid.UUID, Query()],
) -> None:
    await file_service.delete_file(db, session_id, file_id)
