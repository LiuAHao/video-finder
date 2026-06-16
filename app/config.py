"""Configuration management."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from .constants import (
    DEFAULT_CONCURRENCY,
    DEFAULT_DATABASE_PATH,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_USER_AGENT,
    DEFAULT_WAIT_SECONDS,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"
LOG_DIR_PATH = PROJECT_ROOT / "logs"


def resolve_project_path(path_value: str) -> str:
    """Resolve a user-provided path against the project root.

    Relative paths are anchored to the repository root so local config, downloads,
    and SQLite history always persist in the same project directory regardless of
    the shell's current working directory.
    """
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path.resolve())


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
    ffmpeg_path: str = Field(default="", description="Optional full ffmpeg executable path")
    ffprobe_path: str = Field(default="", description="Optional ffprobe executable path")

    # User Agent
    user_agent: str = Field(default=DEFAULT_USER_AGENT, description="User-Agent string")

    # Web server settings
    host: str = Field(default=DEFAULT_HOST, description="Server host")
    port: int = Field(default=DEFAULT_PORT, description="Server port")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")

    model_config = {
        "env_prefix": "VIDEO_FINDER_",
        "env_file": str(ENV_FILE_PATH),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @field_validator("download_dir", "database_path", mode="after")
    @classmethod
    def _normalize_local_paths(cls, value: str) -> str:
        """Keep persisted local paths stable across restarts and launch locations."""
        return resolve_project_path(value)

    def ensure_directories(self) -> None:
        """Ensure required directories exist."""
        Path(self.download_dir).mkdir(parents=True, exist_ok=True)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        LOG_DIR_PATH.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
