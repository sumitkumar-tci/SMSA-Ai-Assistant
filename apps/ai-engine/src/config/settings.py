from __future__ import annotations

from functools import lru_cache

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """
    Central configuration for the AI engine.

    Values are loaded from environment variables but have sensible defaults
    for local development.
    """

    # SMSA tracking API
    smsa_tracking_base_url: str = Field(
        "http://smsaweb.cloudapp.net:8080/track.svc", env="SMSA_TRACKING_BASE_URL"
    )
    smsa_tracking_username: str = Field("aiagent26", env="SMSA_TRACKING_USERNAME")
    smsa_tracking_password: str = Field("mERti8P2", env="SMSA_TRACKING_PASSWORD")

    # Deepseek / LLM (placeholders for future use)
    deepseek_api_key: str | None = Field(default=None, env="DEEPSEEK_API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

