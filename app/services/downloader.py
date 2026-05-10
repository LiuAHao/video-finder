"""Download manager for coordinating downloads."""

import asyncio
from typing import Optional, Callable
from pathlib import Path

from ..config import get_settings
from ..schemas import MediaType, DownloaderType
from ..services.progress import ProgressInfo, ProgressTracker
from ..services.storage import StorageService
from ..downloaders.base import BaseDownloader, DownloadResult
from ..downloaders.ytdlp import YtdlpDownloader
from ..downloaders.ffmpeg import FFmpegDownloader
from ..downloaders.http import HttpDownloader


class DownloadTask:
    """Download task wrapper."""

    def __init__(
        self,
        task_id: str,
        url: str,
        media_type: MediaType,
        output_path: str,
        downloader_type: DownloaderType,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        self.task_id = task_id
        self.url = url
        self.media_type = media_type
        self.output_path = output_path
        self.downloader_type = downloader_type
        self.referer = referer
        self.user_agent = user_agent
        self.downloader: Optional[BaseDownloader] = None
        self.result: Optional[DownloadResult] = None


class DownloadManager:
    """Manage download tasks."""

    def __init__(self):
        self.settings = get_settings()
        self.progress_tracker = ProgressTracker()
        self.storage = StorageService()
        self._active_tasks: dict[str, DownloadTask] = {}

    def select_downloader(
        self,
        media_type: MediaType,
        preferred: DownloaderType = DownloaderType.AUTO,
    ) -> DownloaderType:
        """Select appropriate downloader based on media type."""
        if preferred != DownloaderType.AUTO:
            return preferred

        # Auto selection based on media type
        if media_type == MediaType.PAGE_EXTRACT:
            return DownloaderType.YT_DLP
        elif media_type == MediaType.HLS:
            return DownloaderType.YT_DLP
        elif media_type == MediaType.DASH:
            return DownloaderType.YT_DLP
        elif media_type == MediaType.DIRECT_VIDEO:
            return DownloaderType.YT_DLP
        else:
            return DownloaderType.YT_DLP

    def create_downloader(
        self,
        task_id: str,
        url: str,
        media_type: MediaType,
        output_path: str,
        downloader_type: DownloaderType,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        concurrency: int = 8,
        external_on_progress: Optional[Callable[[ProgressInfo], None]] = None,
    ) -> BaseDownloader:
        """Create downloader instance."""

        def handle_progress(info: ProgressInfo):
            self.progress_tracker.update(
                task_id,
                progress=info.progress,
                speed=info.speed,
                eta=info.eta,
                downloaded_bytes=info.downloaded_bytes,
                total_bytes=info.total_bytes,
                status=info.status,
                message=info.message,
                stage=info.stage,
                elapsed_seconds=info.elapsed_seconds,
                file_size_bytes=info.file_size_bytes,
                logs=info.logs,
            )
            if external_on_progress:
                external_on_progress(info)

        if downloader_type == DownloaderType.YT_DLP:
            return YtdlpDownloader(
                url=url,
                output_path=output_path,
                referer=referer,
                user_agent=user_agent,
                on_progress=handle_progress,
                concurrency=concurrency,
            )
        elif downloader_type == DownloaderType.FFMPEG:
            return FFmpegDownloader(
                url=url,
                output_path=output_path,
                referer=referer,
                user_agent=user_agent,
                on_progress=handle_progress,
                media_type=media_type.value if media_type else None,
            )
        elif downloader_type == DownloaderType.HTTP:
            return HttpDownloader(
                url=url,
                output_path=output_path,
                referer=referer,
                user_agent=user_agent,
                on_progress=handle_progress,
            )
        else:
            raise ValueError(f"Unknown downloader type: {downloader_type}")

    async def start_download(
        self,
        task_id: str,
        url: str,
        media_type: MediaType,
        output_path: str,
        downloader_type: DownloaderType = DownloaderType.AUTO,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        concurrency: int = 8,
        on_progress: Optional[Callable[[ProgressInfo], None]] = None,
    ) -> DownloadResult:
        """Start a download task."""
        # Select downloader
        selected_type = self.select_downloader(media_type, downloader_type)

        # Create downloader
        downloader = self.create_downloader(
            task_id=task_id,
            url=url,
            media_type=media_type,
            output_path=output_path,
            downloader_type=selected_type,
            referer=referer,
            user_agent=user_agent,
            concurrency=concurrency,
            external_on_progress=on_progress,
        )

        # Store task
        task = DownloadTask(
            task_id=task_id,
            url=url,
            media_type=media_type,
            output_path=output_path,
            downloader_type=selected_type,
            referer=referer,
            user_agent=user_agent,
        )
        task.downloader = downloader
        self._active_tasks[task_id] = task

        # Update progress
        self.progress_tracker.update(task_id, status="running")

        # Start download
        result = await downloader.download()

        # If yt-dlp failed for HLS/DASH, try ffmpeg as fallback
        if not result.success and selected_type == DownloaderType.YT_DLP and media_type in (MediaType.HLS, MediaType.DASH):
            self.progress_tracker.update(task_id, status="running", message="yt-dlp 失败，尝试 ffmpeg 下载...")
            ffmpeg_dl = FFmpegDownloader(
                url=url,
                output_path=output_path,
                referer=referer,
                user_agent=user_agent,
                on_progress=lambda info: self.progress_tracker.update(
                    task_id,
                    progress=info.progress,
                    speed=info.speed,
                    eta=info.eta,
                    downloaded_bytes=info.downloaded_bytes,
                    total_bytes=info.total_bytes,
                    status=info.status,
                    message=info.message,
                    stage=info.stage,
                    elapsed_seconds=info.elapsed_seconds,
                    file_size_bytes=info.file_size_bytes,
                    logs=info.logs,
                ),
                media_type=media_type.value,
            )
            result = await ffmpeg_dl.download()

        # Update task result
        task.result = result

        # Update progress
        if result.success:
            self.progress_tracker.update(
                task_id,
                status="completed",
                progress=100.0,
            )
        else:
            self.progress_tracker.update(
                task_id,
                status="failed",
                message=result.error_message,
            )

        # Remove from active tasks
        self._active_tasks.pop(task_id, None)

        return result

    async def cancel_download(self, task_id: str) -> bool:
        """Cancel a download task."""
        task = self._active_tasks.get(task_id)
        if task and task.downloader:
            await task.downloader.cancel()
            self.progress_tracker.update(task_id, status="cancelled")
            self._active_tasks.pop(task_id, None)
            return True
        return False

    def get_progress(self, task_id: str) -> Optional[ProgressInfo]:
        """Get download progress."""
        return self.progress_tracker.get_progress(task_id)

    def get_active_tasks(self) -> list[str]:
        """Get list of active task IDs."""
        return list(self._active_tasks.keys())
