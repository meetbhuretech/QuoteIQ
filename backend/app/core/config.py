"""Runtime configuration. Secrets come from the environment, never from source."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://quoteiq:quoteiq@localhost:5432/quoteiq"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_exp_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    storage_backend: str = "local"
    storage_dir: str = "./storage"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "us-east-1"
    process_inline: bool = True
    process_sync: bool = False
    max_upload_mb: int = 25
    model_artifact_dir: str = "../ml/artifacts"
    mlflow_tracking_uri: str | None = None
    confidence_review_threshold: float = 0.75
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production and settings.jwt_secret in {"change-me", "replace-with-a-long-random-string"}:
        raise RuntimeError("JWT_SECRET must be set to a unique value in production")
    return settings
