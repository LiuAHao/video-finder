"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class MediaType(str, Enum):
    """Media resource types."""
    HLS = "hls"
    DASH = "dash"
    DIRECT_VIDEO = "direct_video"
    PAGE_EXTRACT = "page_extract"
    BLOB_HINT = "blob_hint"
    UNKNOWN = "unknown"


class DiscoveryMethod(str, Enum):
    """Discovery methods."""
    NETWORK = "network"
    HTML = "html"
    PLAYER_CONFIG = "player_config"
    YT_DLP = "yt_dlp"


class TaskStatus(str, Enum):
    """Task status."""
    PENDING = "pending"
    RUNNING = "running"
    DOWNLOADING = "downloading"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DownloaderType(str, Enum):
    """Downloader types."""
    AUTO = "auto"
    YT_DLP = "ytdlp"
    FFMPEG = "ffmpeg"
    HTTP = "http"


# Sniff Schemas

class SniffRequest(BaseModel):
    """Sniff task request."""
    page_url: str = Field(..., description="Page URL to sniff")
    wait_seconds: int = Field(default=10, ge=1, le=60, description="Wait time in seconds")
    auto_click: bool = Field(default=True, description="Auto click play button")
    headless: bool = Field(default=True, description="Run browser in headless mode")
    user_agent: Optional[str] = Field(default=None, description="Custom User-Agent")
    referer: Optional[str] = Field(default=None, description="Custom Referer")


class SniffResponse(BaseModel):
    """Sniff task response."""
    task_id: str
    status: TaskStatus


class MediaCandidateResponse(BaseModel):
    """Media candidate response."""
    id: str
    media_url: str
    media_type: MediaType
    discovery_method: DiscoveryMethod
    source_frame_url: Optional[str] = None
    content_type: Optional[str] = None
    http_status: Optional[int] = None
    referer: Optional[str] = None
    user_agent: Optional[str] = None
    title: Optional[str] = None
    resolution: Optional[str] = None
    bandwidth: Optional[int] = None
    filesize: Optional[int] = None
    is_temporary: bool = False
    score: int = 0

    class Config:
        from_attributes = True


class SniffResultResponse(BaseModel):
    """Sniff result response."""
    task_id: str
    status: TaskStatus
    page_url: str
    candidates: list[MediaCandidateResponse] = []
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# Download Schemas

class DownloadRequest(BaseModel):
    """Download task request."""
    candidate_id: str = Field(..., description="Media candidate ID")
    downloader: DownloaderType = Field(default=DownloaderType.AUTO, description="Downloader to use")
    output_name: Optional[str] = Field(default=None, description="Output filename")
    download_dir: Optional[str] = Field(default=None, description="Download directory")
    concurrency: int = Field(default=8, ge=1, le=32, description="Concurrent connections")


class DownloadResponse(BaseModel):
    """Download task response."""
    download_id: str
    status: TaskStatus


class DownloadProgressResponse(BaseModel):
    """Download progress response."""
    download_id: str
    status: TaskStatus
    progress: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    output_path: Optional[str] = None
    downloaded_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    error_message: Optional[str] = None
    media_type: Optional[str] = None
    segment_current: Optional[int] = None
    segment_total: Optional[int] = None
    stage: Optional[str] = None
    elapsed_seconds: Optional[int] = None
    file_size_bytes: Optional[int] = None
    logs: Optional[list[str]] = None


# History Schemas

class HistoryItem(BaseModel):
    """History item."""
    id: str
    page_url: str
    status: TaskStatus
    media_type: Optional[str] = None
    resolution: Optional[str] = None
    output_path: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HistoryResponse(BaseModel):
    """History list response."""
    items: list[HistoryItem]
    total: int


# Config Schemas

class ConfigResponse(BaseModel):
    """Configuration response."""
    download_dir: str
    database_path: str
    headless: bool
    wait_seconds: int
    auto_click: bool
    default_downloader: str
    concurrency: int
    user_agent: str


class ConfigUpdate(BaseModel):
    """Configuration update request."""
    download_dir: Optional[str] = None
    headless: Optional[bool] = None
    wait_seconds: Optional[int] = None
    auto_click: Optional[bool] = None
    default_downloader: Optional[DownloaderType] = None
    concurrency: Optional[int] = None
    user_agent: Optional[str] = None


# Log Schema

class LogEntry(BaseModel):
    """Log entry."""
    id: str
    task_id: str
    task_type: str
    level: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True
