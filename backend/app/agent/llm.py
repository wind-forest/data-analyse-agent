from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import (
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

from app.config import settings
from app.errors import AppError

logger = logging.getLogger("app.agent.llm")

_client: AsyncOpenAI | None = None


@dataclass
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    total_tokens: int = 0


def _get_client() -> AsyncOpenAI:
    global _client
    if not settings.llm_configured:
        raise AppError("LLM_NOT_CONFIGURED", "未配置 DeepSeek API Key", 503)
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.simple_query_timeout_seconds,
            max_retries=0,
        )
    return _client


def _classify_error(exc: Exception) -> AppError:
    if isinstance(exc, AuthenticationError | PermissionDeniedError):
        return AppError("LLM_AUTH_ERROR", "模型服务鉴权失败，请检查 API Key", 502)
    if isinstance(exc, RateLimitError):
        return AppError("LLM_RATE_LIMITED", "模型服务限流，请稍后重试", 502)
    if isinstance(exc, APITimeoutError | TimeoutError):
        return AppError("LLM_TIMEOUT", "模型服务超时", 504)
    return AppError("LLM_ERROR", f"模型服务调用失败: {type(exc).__name__}", 502)


async def chat_completion(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> LLMResponse:
    client = _get_client()
    request: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    if tools:
        request["tools"] = tools
        request["tool_choice"] = "auto"

    last_error: AppError | None = None
    for attempt in range(2):
        try:
            completion = await client.chat.completions.create(**request)
            choice = completion.choices[0]
            message = choice.message
            calls: list[LLMToolCall] = []
            for call in message.tool_calls or []:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except ValueError:
                    arguments = {"__invalid_arguments__": call.function.arguments}
                if not isinstance(arguments, dict):
                    arguments = {"__invalid_arguments__": arguments}
                calls.append(
                    LLMToolCall(
                        id=call.id,
                        name=call.function.name,
                        arguments=arguments,
                    )
                )
            usage = completion.usage
            return LLMResponse(
                content=message.content or "",
                tool_calls=calls,
                total_tokens=int(usage.total_tokens) if usage else 0,
            )
        except Exception as exc:  # noqa: BLE001 - 需要按上游类型分类
            error = _classify_error(exc)
            last_error = error
            retryable = error.code in {"LLM_RATE_LIMITED", "LLM_TIMEOUT"}
            if attempt == 0 and retryable:
                logger.warning("llm transient error code=%s, retrying", error.code)
                await asyncio.sleep(1.0)
                continue
            break

    assert last_error is not None
    logger.error("llm call failed code=%s", last_error.code)
    raise last_error
