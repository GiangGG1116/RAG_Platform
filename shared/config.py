"""
Centralized configuration using Pydantic Settings.

All microservices import from this module to ensure consistent
environment variable handling across the platform.
"""
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── PostgreSQL ───────────────────────────────────────
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "rag_platform"
    postgres_user: str = "rag_user"
    postgres_password: str = "rag_secret_password"  # noqa: S105

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ────────────────────────────────────────────
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── RabbitMQ ─────────────────────────────────────────
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "rag_user"
    rabbitmq_password: str = "rag_secret_password"  # noqa: S105
    rabbitmq_vhost: str = "/"

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
        )

    # ── LLM ──────────────────────────────────────────────
    llm_provider: Literal["openai", "local"] = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # ── Service URLs ─────────────────────────────────────
    api_gateway_host: str = "0.0.0.0"
    api_gateway_run_port: int = 8000
    ingestion_service_url: str = "http://ingestion:8001"
    retrieval_service_url: str = "http://retrieval:8002"
    llm_service_url: str = "http://llm-service:8003"

    # ── Auth ─────────────────────────────────────────────
    api_key_header: str = "X-API-Key"
    api_keys: str = "default-api-key-change-me"
    jwt_secret_key: str = "change-me-to-a-secure-random-string-in-production"  # noqa: S105
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    @property
    def api_keys_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    # ── CORS ─────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ── Rate Limiting ────────────────────────────────────
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # ── Observability ────────────────────────────────────
    otel_exporter_otlp_endpoint: str = "http://otel-collector:4317"
    otel_service_name: str = "rag-platform"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # ── Chunking ─────────────────────────────────────────
    chunk_size: int = 512
    chunk_overlap: int = 50

    # ── Memory (Conversation History) ────────────────────
    memory_max_turns: int = 10
    memory_ttl_seconds: int = 3600

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            msg = f"log_level must be one of {allowed}"
            raise ValueError(msg)
        return upper


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton settings instance."""
    return Settings()
