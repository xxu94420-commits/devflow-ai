from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/devflow.db"
    github_token: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    devflow_api_key: str = ""
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


@lru_cache
def get_settings():
    return Settings()
