from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，全部来自环境变量或本地 .env。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Data Analysis Agent"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://data_agent:data_agent@postgres:5432/data_agent"
    redis_url: str = "redis://redis:6379/0"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com"
    model_name: str = "deepseek-chat"
    allowed_models: str = "deepseek-chat"

    data_dir: str = "/data"
    host_data_dir: str = ""
    sandbox_image: str = "data-agent-sandbox:latest"

    max_upload_size_mb: int = 2048
    analysis_timezone: str = "Asia/Shanghai"

    max_iterations: int = 10
    agent_recursion_limit: int = 30
    simple_query_timeout_seconds: int = 30
    modeling_timeout_seconds: int = 120
    agent_token_budget: int = 32768

    sse_event_ttl_seconds: int = 86400
    sse_heartbeat_seconds: int = 15

    approval_timeout_seconds: int = 300
    sandbox_timeout_seconds: int = 30
    sandbox_memory: str = "512m"

    app_http_port: int = 18080
    app_bind_address: str = "127.0.0.1"

    # Auth
    auth_enabled: bool = True
    auth_secret_key: str = "change-me-in-production-please-use-a-random-string"
    auth_session_cookie: str = "data_agent_session"
    auth_session_ttl_seconds: int = 7 * 24 * 3600  # 7 days
    auth_captcha_ttl_seconds: int = 300  # 5 minutes
    anon_max_sessions: int = 2
    anon_max_messages_per_session: int = 3

    @property
    def allowed_model_list(self) -> list[str]:
        return [item.strip() for item in self.allowed_models.split(",") if item.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
