"""Configuration management."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

from .constants import (
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_DATABASE_PATH,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_WAIT_SECONDS,
    DEFAULT_CONCURRENCY,
    DEFAULT_USER_AGENT,
)


class Settings(BaseSettings):
    """Application settings."""

    # Paths
    download_dir: str = Field(default=DEFAULT_DOWNLOAD_DIR, description="Download directory")
    database_path: str = Field(default=DEFAULT_DATABASE_PATH, description="SQLite database path")

    # Browser settings
    headless: bool = Field(default=True, description="Run browser in headless mode")
    wait_seconds: int = Field(default=DEFAULT_WAIT_SECONDS, ge=1, le=60, description="Wait time for page loading")
    auto_click: bool = Field(default=True, description="Auto click play button")

    # Downloader settings
    default_downloader: str = Field(default="auto", description="Default downloader: auto, ytdlp, ffmpeg, http")
    concurrency: int = Field(default=DEFAULT_CONCURRENCY, ge=1, le=32, description="Concurrent connections")

    # User Agent
    user_agent: str = Field(default=DEFAULT_USER_AGENT, description="User-Agent string")

    # Web server settings
    host: str = Field(default=DEFAULT_HOST, description="Server host")
    port: int = Field(default=DEFAULT_PORT, description="Server port")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")

    model_config = {
        "env_prefix": "VIDEO_FINDER_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path("./logs").mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
