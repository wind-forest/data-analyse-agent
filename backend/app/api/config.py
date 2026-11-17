from fastapi import APIRouter

from app.config import settings
from app.sandbox.manager import is_available
from app.schemas.config import ConfigRead

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigRead)
async def get_config() -> ConfigRead:
    return ConfigRead(
        default_model=settings.model_name,
        allowed_models=settings.allowed_model_list,
        max_upload_size_mb=settings.max_upload_size_mb,
        custom_code_available=is_available(),
    )
