from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Central configuration for the AI engine.

    Values are loaded from environment variables but have sensible defaults
    for local development.
    """

    # SMSA Tracking API (Phase 0 - DONE)
    smsa_tracking_base_url: str = Field(
        "http://smsaweb.cloudapp.net:8080/track.svc", env="SMSA_TRACKING_BASE_URL"
    )
    smsa_tracking_username: str = Field("aiagent26", env="SMSA_TRACKING_USERNAME")
    smsa_tracking_password: str = Field("mERti8P2", env="SMSA_TRACKING_PASSWORD")

    # SMSA Rates API (Phase 2)
    smsa_rates_base_url: str = Field(
        "https://mobileapi.smsaexpress.com/SmsaMobileWebServiceRestApi/api/RateInquiry/inquiry",
        env="SMSA_RATES_BASE_URL",
    )
    smsa_rates_passkey: str = Field("riai$ervice", env="SMSA_RATES_PASSKEY")

    # SMSA Retail Centers API (Phase 2)
    smsa_retail_base_url: str = Field(
        "https://mobileapi.smsaexpress.com/smsamobilepro/retailcenter.asmx",
        env="SMSA_RETAIL_BASE_URL",
    )
    smsa_retail_passkey: str = Field("rcai$ervice", env="SMSA_RETAIL_PASSKEY")

    # Self-Hosted LLM Models (Phase 3)
    # Text Model for chat/intent/FAQ
    llm_text_api_url: str = Field(
        "https://api-me-east-1.modelarts-maas.com/v2/chat/completions",
        env="LLM_TEXT_API_URL",
    )
    llm_text_model: str = Field("qwen3-32b-icDAJO", env="LLM_TEXT_MODEL")
    llm_api_key: str = Field(
        "ok1HeIp7xMOPyMDCS_-7vbZnX5sZKMV_Kc6lT1lD2gstrwPzGGrdcEWbuPsg-7gLu8V0qH99DuCNa8U5ocBCJw",
        env="LLM_API_KEY",
    )
    
    # Vision Model for OCR/image analysis
    llm_vision_api_url: str = Field(
        "https://api-me-east-1.modelarts-maas.com/v2/chat/completions",
        env="LLM_VISION_API_URL",
    )
    llm_vision_model: str = Field(
        "Qwen3-VL-32B-Instruct-yjBcMV", env="LLM_VISION_MODEL"
    )

    # Huawei Cloud OBS / File Storage (Phase 4)
    huawei_obs_endpoint: str | None = Field(default=None, env="HUAWEI_OBS_ENDPOINT")
    huawei_obs_bucket_name: str | None = Field(default=None, env="HUAWEI_OBS_BUCKET_NAME")
    huawei_obs_access_key_id: str | None = Field(default=None, env="HUAWEI_OBS_ACCESS_KEY_ID")
    huawei_obs_secret_access_key: str | None = Field(default=None, env="HUAWEI_OBS_SECRET_ACCESS_KEY")

    # MongoDB (Phase 6)
    mongodb_uri: str = Field(
        "mongodb://localhost:27017/smsa_ai_assistant", env="MONGODB_URI"
    )

    # Vector DB - Qdrant (Phase 6)
    qdrant_url: str = Field("http://localhost:6333", env="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, env="QDRANT_API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

