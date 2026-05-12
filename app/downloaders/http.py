"""HTTP downloader implementation."""

import asyncio
from typing import Optional, Callable
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .base import BaseDownloader, DownloadResult
from ..services.progress import ProgressInfo


class HttpDownloader(BaseDownloader):
    """Simple HTTP downloader."""

    def __init__(
        self,
        url: str,
        output_path: str,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        on_progress: Optional[Callable[[ProgressInfo], None]] = None,
        chunk_size: int = 8192,
    ):
        super().__init__(url, output_path, referer, user_agent, on_progress)
        self.chunk_size = chunk_size

    def get_command(self) -> list[str]:
        """Not used for HTTP downloader."""
        return []

    async def download(self) -> DownloadResult:
        """Download file via HTTP."""
        self._ensure_output_dir()

        try:
            headers = {}
            if self.referer:
                headers["Referer"] = self.referer
            if self.user_agent:
                headers["User-Agent"] = self.user_agent

            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "GET",
                    self.url,
                    headers=headers,
                    follow_redirects=True,
                    timeout=30,
                ) as response:
                    response.raise_for_status()

                    # Get total size
                    total_size = int(response.headers.get("content-length", 0))

                    downloaded = 0
                    with open(self.output_path, "wb") as f:
                        async for chunk in response.aiter_bytes(self.chunk_size):
                            if self._cancelled:
                                return DownloadResult(
                                    success=False,
                                    error_message="Download cancelled",
                                    cancelled=True,
                                )

                            f.write(chunk)
                            downloaded += len(chunk)

                            # Report progress
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                self._report_progress(ProgressInfo(
                                    progress=progress,
                                    downloaded_bytes=downloaded,
                                    total_bytes=total_size,
                                    status="downloading",
                                ))

                    # Get final file size
                    file_size = Path(self.output_path).stat().st_size

                    self._report_progress(ProgressInfo(
                        progress=100.0,
                        status="completed",
                    ))

                    return DownloadResult(
                        success=True,
                        output_path=self.output_path,
                        file_size=file_size,
                    )

        except httpx.HTTPStatusError as e:
            return DownloadResult(
                success=False,
                error_message=f"HTTP error {e.response.status_code}: {e.response.reason_phrase}",
            )
        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=f"Download error: {e}",
            )

    async def cancel(self) -> None:
        """Cancel the download."""
        self._cancelled = True

    @staticmethod
    def get_filename_from_url(url: str) -> str:
        """Extract filename from URL."""
        parsed = urlparse(url)
        path = parsed.path
        if path:
            filename = Path(path).name
            if filename and "." in filename:
                return filename
        return "download"
