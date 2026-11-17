from pydantic import BaseModel


class ConfigRead(BaseModel):
    default_model: str
    allowed_models: list[str]
    max_upload_size_mb: int
    custom_code_available: bool
