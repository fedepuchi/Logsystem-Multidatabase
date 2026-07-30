from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOGMON_", env_file=".env", extra="ignore")

    sqlite_path: str = "metadata.db"
    static_dir: Optional[str] = None
    cors_origins: List[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()