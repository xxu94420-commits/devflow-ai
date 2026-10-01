from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/devflow.db"
    github_token: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    devflow_api_key: str = ""
    read_only: bool = False
    static_dir: str = ""
    demo_import_github: bool = False
    ci_sync_interval_seconds: int = Field(default=0, ge=0, le=86400)
    review_api_base_url: str = ""
    review_api_key: str = ""
    review_model: str = ""
    review_ollama_enabled: bool = False
    review_ollama_base_url: str = "http://127.0.0.1:11434/v1"
    review_ollama_model: str = ""
    public_review_enabled: bool = False
    public_review_daily_limit: int = Field(default=20, ge=1, le=100)

    @field_validator("ci_sync_interval_seconds")
    @classmethod
    def bounded_interval(cls, value):
        if 0 < value < 300:
            raise ValueError("CI sync interval must be 0 (disabled) or >=300 seconds")
        return value

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


@lru_cache
def get_settings():
    return Settings()
