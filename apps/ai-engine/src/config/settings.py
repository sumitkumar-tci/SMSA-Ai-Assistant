from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

# Get project root directory
# This file: apps/ai-engine/src/config/settings.py
# Project root: SMSA-Ai-Assistant/ (where .env should be)
# Path calculation: config -> src -> ai-engine -> apps -> SMSA-Ai-Assistant
_current_file = Path(__file__).resolve()
PROJECT_ROOT = _current_file.parent.parent.parent.parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"

# Also try relative to current working directory as fallback
import os
_cwd_env = Path(os.getcwd()) / ".env"
if not ENV_FILE_PATH.exists() and _cwd_env.exists():
    ENV_FILE_PATH = _cwd_env


class SMSAAIAssistantSettings(BaseSettings):
    """
    Central configuration for the AI engine.

    Values are loaded from environment variables but have sensible defaults
    for local development.
    """

    # SMSA Tracking API (Phase 0 - DONE)
    smsa_tracking_base_url: str = Field(
        default="http://smsaweb.cloudapp.net:8080/track.svc", env="SMSA_TRACKING_BASE_URL"
    )
    smsa_tracking_username: str = Field(default="", env="SMSA_TRACKING_USERNAME")
    smsa_tracking_password: str = Field(default="", env="SMSA_TRACKING_PASSWORD")

    # SMSA Rates API (Phase 2)
    smsa_rates_base_url: str = Field(
        default="https://mobileapi.smsaexpress.com/SmsaMobileWebServiceRestApi/api/RateInquiry/inquiry",
        env="SMSA_RATES_BASE_URL",
    )
    smsa_rates_passkey: str = Field(default="", env="SMSA_RATES_PASSKEY")

    # SMSA Retail Centers API (Phase 2)
    smsa_retail_base_url: str = Field(
        default="https://mobileapi.smsaexpress.com/smsamobilepro/retailcenter.asmx",
        env="SMSA_RETAIL_BASE_URL",
    )
    smsa_retail_passkey: str = Field(default="", env="SMSA_RETAIL_PASSKEY")

    # Self-Hosted LLM Models (Phase 3)
    # Text Model for chat/intent/FAQ
    llm_text_api_url: str = Field(
        default="https://api-me-east-1.modelarts-maas.com/v2/chat/completions",
        env="LLM_TEXT_API_URL",
    )
    llm_text_model: str = Field(default="qwen3-32b-icDAJO", env="LLM_TEXT_MODEL")
    llm_api_key: str = Field(default="", env="LLM_API_KEY")
    
    # Vision Model for OCR/image analysis
    llm_vision_api_url: str = Field(
        default="https://api-me-east-1.modelarts-maas.com/v2/chat/completions",
        env="LLM_VISION_API_URL",
    )
    llm_vision_model: str = Field(
        default="Qwen3-VL-32B-Instruct-yjBcMV", env="LLM_VISION_MODEL"
    )

    # Huawei Cloud OBS / File Storage (Phase 4)
    huawei_obs_endpoint: str = Field(
        default="obs.me-east-1.myhuaweicloud.com", env="HUAWEI_OBS_ENDPOINT"
    )
    huawei_obs_bucket_name: str = Field(
        default="smsa-ai-agent", env="HUAWEI_OBS_BUCKET_NAME"
    )
    huawei_obs_access_key_id: str = Field(default="", env="HUAWEI_OBS_ACCESS_KEY_ID")
    huawei_obs_secret_access_key: str = Field(default="", env="HUAWEI_OBS_SECRET_ACCESS_KEY")
    huawei_obs_region: str = Field("me-east-1", env="HUAWEI_OBS_REGION")
    huawei_obs_access_domain: str = Field(
        "smsa-ai-agent.obs.me-east-1.myhuaweicloud.com", env="HUAWEI_OBS_ACCESS_DOMAIN"
    )

    # MongoDB (Phase 6)
    mongodb_uri: str = Field(
        "mongodb://localhost:27017/smsa_ai_assistant", env="MONGODB_URI"
    )

    # Vector DB - Qdrant (Phase 6)
    qdrant_url: str = Field("http://localhost:6333", env="QDRANT_URL")
    qdrant_api_key: str | None = Field(default=None, env="QDRANT_API_KEY")

    class Config:
        env_file = str(ENV_FILE_PATH)  # Load from project root
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> SMSAAIAssistantSettings:
    from ..logging_config import logger
    
    # Debug: Log which .env file path we're using
    logger.info(
        "loading_env_file",
        env_file_path=str(ENV_FILE_PATH),
        exists=ENV_FILE_PATH.exists(),
    )
    
    settings = SMSAAIAssistantSettings()
    
    # Check if API key was loaded
    if not settings.llm_api_key:
        logger.warning(
            "llm_api_key_empty",
            env_file_path=str(ENV_FILE_PATH),
            env_file_exists=ENV_FILE_PATH.exists(),
        )
    
    return settings


settings = get_settings()

