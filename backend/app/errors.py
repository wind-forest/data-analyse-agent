from __future__ import annotations

from typing import Any


class AppError(Exception):
    """带稳定错误码的业务异常，统一转换为 API 错误响应。"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
