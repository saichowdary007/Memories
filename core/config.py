from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import AnyHttpUrl, Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SETTINGS__", env_nested_delimiter="__", extra="ignore")

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_origins: List[AnyHttpUrl] = Field(default_factory=list)

    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="neo4jpassword")

    valkey_host: str = Field(default="localhost")
    valkey_port: int = Field(default=6379)

    minio_endpoint: str = Field(default="http://localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_secure: bool = Field(default=False)
    minio_bucket: str = Field(default="pkb-artifacts")

    lancedb_uri: str = Field(default="./data/lancedb")

    ollama_host: str = Field(default="http://localhost:11434")
    embeddings_model: str = Field(default="BAAI/bge-m3")
    image_embeddings_model: str = Field(default="google/siglip-base-patch16-384")
    reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3")
    reranker_fallback_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    llm_model: str = Field(default="qwen2.5:7b-instruct-q4_K_M")
    vision_model: str = Field(default="paligemma-3b:latest")
    speech_model: str = Field(default="whisper-large-v3-turbo")

    jwt_secret_key: str = Field(default="super-secret-key")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60)

    rate_limit: int = Field(default=60)

    prometheus_port: int = Field(default=9001)

    worker_broker_uri: str = Field(default="valkey://localhost:6379/0")
    backpressure_free_mem_bytes: int = Field(default=1_610_612_736)  # 1.5GB
    max_workers: int = Field(default=4)
    mps_monitor_interval: int = Field(default=5)

    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_refresh_token: Optional[str] = None
    google_project_id: Optional[str] = None
    google_redirect_uri: Optional[str] = None

    slack_bot_token: Optional[str] = None
    slack_app_token: Optional[str] = None

    notion_internal_integration_token: Optional[str] = None

    generic_imap_host: Optional[str] = None
    generic_imap_port: int = Field(default=993)
    generic_imap_username: Optional[str] = None
    generic_imap_password: Optional[str] = None

    obsidian_vault_path: str = Field(default="~/Documents/ObsidianVault")
    chrome_history_path: str = Field(default="~/Library/Application Support/Google/Chrome/Default/History")
    firefox_profile_path: str = Field(default="~/Library/Application Support/Firefox/Profiles")
    google_takeout_path: str = Field(default="~/Downloads/Takeout")
    local_watch_paths: List[str] = Field(default_factory=lambda: ["~/Documents"])

    cron_timezone: str = Field(default="UTC")
    backup_path: str = Field(default="./backups")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @validator("cors_origins", pre=True)
    def split_cors(cls, value: str | List[str]) -> List[AnyHttpUrl]:
        if isinstance(value, str):
            if not value:
                return []
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @validator("obsidian_vault_path", "chrome_history_path", "firefox_profile_path", "google_takeout_path")
    def expand_user_paths(cls, value: str) -> str:
        return os.path.expanduser(value)

    @validator("local_watch_paths", pre=True)
    def normalize_watch_paths(cls, value: str | List[str]) -> List[str]:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
        else:
            items = value
        return [os.path.expanduser(item) for item in items]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
