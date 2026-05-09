"""Database models using SQLAlchemy."""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class SniffTask(Base):
    """Sniff task model."""
    __tablename__ = "sniff_tasks"

    id = Column(String, primary_key=True)
    page_url = Column(Text, nullable=False)
    status = Column(String, default="pending")  # pending, running, completed, failed
    wait_seconds = Column(Integer, default=10)
    auto_click = Column(Boolean, default=True)
    headless = Column(Boolean, default=True)
    user_agent = Column(Text)
    referer = Column(Text)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)

    candidates = relationship("MediaCandidate", back_populates="sniff_task", cascade="all, delete-orphan")


class MediaCandidate(Base):
    """Media candidate model."""
    __tablename__ = "media_candidates"

    id = Column(String, primary_key=True)
    sniff_task_id = Column(String, ForeignKey("sniff_tasks.id"), nullable=False)
    page_url = Column(Text, nullable=False)
    media_url = Column(Text, nullable=False)
    media_type = Column(String, nullable=False)  # hls, dash, direct_video, page_extract, blob_hint, unknown
    discovery_method = Column(String, nullable=False)  # network, html, player_config, yt_dlp
    source_frame_url = Column(Text)
    content_type = Column(String)
    http_status = Column(Integer)
    referer = Column(Text)
    user_agent = Column(Text)
    title = Column(Text)
    resolution = Column(String)
    bandwidth = Column(Integer)
    filesize = Column(Integer)
    is_temporary = Column(Boolean, default=False)
    score = Column(Integer, default=0)
    raw_info_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    sniff_task = relationship("SniffTask", back_populates="candidates")
    download_tasks = relationship("DownloadTask", back_populates="candidate")


class DownloadTask(Base):
    """Download task model."""
    __tablename__ = "download_tasks"

    id = Column(String, primary_key=True)
    candidate_id = Column(String, ForeignKey("media_candidates.id"), nullable=False)
    url = Column(Text, nullable=False)
    downloader = Column(String, nullable=False)  # ytdlp, ffmpeg, http
    status = Column(String, default="pending")  # pending, running, downloading, merging, completed, failed, cancelled
    output_path = Column(Text)
    progress = Column(Float, default=0.0)
    speed = Column(String)
    eta = Column(String)
    downloaded_bytes = Column(Integer)
    total_bytes = Column(Integer)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)

    candidate = relationship("MediaCandidate", back_populates="download_tasks")
    logs = relationship("TaskLog", back_populates="task", cascade="all, delete-orphan")


class TaskLog(Base):
    """Task log model."""
    __tablename__ = "task_logs"

    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("download_tasks.id"), nullable=False)
    task_type = Column(String, nullable=False)  # sniff, download
    level = Column(String, nullable=False)  # info, warning, error
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("DownloadTask", back_populates="logs")
