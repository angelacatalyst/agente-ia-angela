"""Application configuration — Pydantic-Settings v2."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split(raw: str) -> list[str]:
    """Parse comma-separated or JSON-array string → list."""
    v = raw.strip()
    if not v:
        return []
    if v.startswith("["):
        import json
        try:
            return [str(i).strip() for i in json.loads(v) if str(i).strip()]
        except Exception:
            pass
    return [i.strip() for i in v.split(",") if i.strip()]


class Environment(str, Enum):
    development = "development"
    staging = "staging"
    production = "production"


class LogFormat(str, Enum):
    json = "json"
    console = "console"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    app_env: Environment = Environment.development
    app_name: str = "Finance Ops AI Manager"
    app_version: str = "0.1.0"
    secret_key: str = "change-me-in-production-minimum-32-chars!!"
    api_key_header: str = "X-API-Key"

    # Store as plain str — pydantic-settings won't JSON-decode plain strings
    api_keys: str = "test-key-123"

    # ── Anthropic ─────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_max_tokens: int = 8192

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./finance_ops.db"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_seconds: int = 3600

    # ── QuickBooks Online ─────────────────────────────────────────────────────
    qbo_client_id: str = ""
    qbo_client_secret: str = ""
    qbo_redirect_uri: str = "http://localhost:8000/api/v1/integrations/qbo/callback"
    qbo_environment: str = "sandbox"
    qbo_base_url_sandbox: str = "https://sandbox-quickbooks.api.intuit.com"
    qbo_base_url_prod: str = "https://quickbooks.api.intuit.com"
    qbo_minor_version: int = 70

    # ── Asana ─────────────────────────────────────────────────────────────────
    asana_access_token: str = ""
    asana_workspace_gid: str = ""
    asana_default_project_gid: str = ""

    # ── Ramp ──────────────────────────────────────────────────────────────────
    ramp_client_id: str = ""
    ramp_client_secret: str = ""
    ramp_base_url: str = "https://api.ramp.com/developer/v1"

    # ── File Upload ───────────────────────────────────────────────────────────
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50
    allowed_extensions: str = "csv,xlsx,xls,pdf,txt,json"

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://localhost:8080"
    cors_allow_credentials: bool = True

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.console

    # ── Computed list properties ───────────────────────────────────────────────
    @computed_field  # type: ignore[misc]
    @property
    def api_keys_list(self) -> list[str]:
        return _split(self.api_keys)

    @computed_field  # type: ignore[misc]
    @property
    def cors_origins_list(self) -> list[str]:
        return _split(self.cors_origins)

    @computed_field  # type: ignore[misc]
    @property
    def allowed_extensions_list(self) -> list[str]:
        return _split(self.allowed_extensions)

    # ── Other computed ─────────────────────────────────────────────────────────
    @computed_field  # type: ignore[misc]
    @property
    def async_database_url(self) -> str:
        """
        Convert bare postgresql:// → postgresql+asyncpg:// for SQLAlchemy async.
        Render (and most PaaS) export plain postgres:// or postgresql:// URLs.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://"):]
        return url

    @computed_field  # type: ignore[misc]
    @property
    def qbo_base_url(self) -> str:
        return (
            self.qbo_base_url_sandbox
            if self.qbo_environment == "sandbox"
            else self.qbo_base_url_prod
        )

    @computed_field  # type: ignore[misc]
    @property
    def is_production(self) -> bool:
        return self.app_env == Environment.production

    @computed_field  # type: ignore[misc]
    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
