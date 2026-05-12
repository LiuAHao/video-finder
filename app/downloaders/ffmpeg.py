"""ffmpeg downloader implementation."""

import asyncio
import os
import shutil
from typing import Optional, Callable
from pathlib import Path

from .base import BaseDownloader, DownloadResult
from ..services.progress import ProgressInfo, FFmpegProgressParser, parse_m3u8_segments


def _resolve_binary(binary_name: str, env_var: str, playwright_fallback: Optional[str] = None) -> Optional[str]:
    """Resolve an executable from PATH, env var, or local Playwright bundle."""
    binary_path = shutil.which(binary_name)
    if binary_path:
        return binary_path

    configured_path = os.environ.get(env_var) or os.environ.get(f"VIDEO_FINDER_{env_var}")
    if configured_path and Path(configured_path).exists():
        return configured_path

    if not playwright_fallback:
        return None

    bundled_path = (
        Path(__file__).resolve().parents[2]
        / "venv"
        / "Lib"
        / "site-packages"
        / "playwright"
        / "driver"
        / "package"
        / ".local-browsers"
    )
    matches = sorted(bundled_path.glob(playwright_fallback), reverse=True)
    if matches:
        return str(matches[0])

    return None


def resolve_ffmpeg_path() -> Optional[str]:
    """Resolve ffmpeg executable path."""
    return _resolve_binary(
        "ffmpeg",
        "FFMPEG_PATH",
    )


def resolve_ffprobe_path() -> Optional[str]:
    """Resolve ffprobe executable path."""
    return _resolve_binary(
        "ffprobe",
        "FFPROBE_PATH",
    )


class FFmpegDownloader(BaseDownloader):
    """ffmpeg downloader for HLS/DASH streams."""

    def __init__(
        self,
        url: str,
        output_path: str,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        on_progress: Optional[Callable[[ProgressInfo], None]] = None,
        total_duration: Optional[float] = None,
        extra_args: Optional[list[str]] = None,
        media_type: Optional[str] = None,
    ):
        super().__init__(url, output_path, referer, user_agent, on_progress)
        self.total_duration = total_duration
        self.extra_args = extra_args or []
        self.media_type = media_type
        self._parser = FFmpegProgressParser(
            total_duration=total_duration,
            media_type=media_type,
        )

    async def _init_segment_count(self) -> None:
        """Parse m3u8 to get total segment count before download."""
        if self.media_type != "hls":
            return
        total = await parse_m3u8_segments(self.url)
        if total:
            self._parser.total_segments = total

    def get_command(self) -> list[str]:
        """Get ffmpeg command."""
        # Find ffmpeg executable
        ffmpeg_path = resolve_ffmpeg_path()
        if not ffmpeg_path:
            raise FileNotFoundError(
                "ffmpeg not found. Please install a full ffmpeg build and ensure it is on PATH "
                "or set FFMPEG_PATH."
            )

        cmd = [
            ffmpeg_path,
            "-y",  # Overwrite output
            "-nostdin",  # No interactive input
        ]

        # Headers - must be formatted properly for ffmpeg
        headers = []
        if self.referer:
            headers.append(f"Referer: {self.referer}")
        if self.user_agent:
            headers.append(f"User-Agent: {self.user_agent}")

        if headers:
            # ffmpeg requires headers to end with \r\n
            header_str = "\r\n".join(headers) + "\r\n"
            cmd.extend(["-headers", header_str])

        # Input URL
        cmd.extend(["-i", self.url])

        # Copy codec (no re-encoding)
        cmd.extend(["-c", "copy"])

        # Disable subtitles
        cmd.extend(["-sn"])

        # Extra args
        cmd.extend(self.extra_args)

        # Output file
        cmd.append(self.output_path)

        return cmd

    async def download(self) -> DownloadResult:
        """Start ffmpeg download."""
        try:
            # Pre-parse m3u8 for segment count
            await self._init_segment_count()
            command = self.get_command()
            return await self._run_process_with_progress(command, self._parse_progress)
        except FileNotFoundError as e:
            return DownloadResult(
                success=False,
                error_message=str(e),
            )
        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=f"ffmpeg error: {e}",
            )

    async def cancel(self) -> None:
        """Cancel the download."""
        self._cancelled = True
        await self._terminate_process()

    def _parse_progress(self, line: str) -> Optional[ProgressInfo]:
        """Parse ffmpeg progress line."""
        return self._parser.parse_line(line)


class FFmpegProbe:
    """Probe media file using ffprobe."""

    async def probe(self, url: str) -> Optional[dict]:
        """Probe URL and return media info."""
        ffprobe_path = resolve_ffprobe_path()
        if not ffprobe_path:
            return None

        cmd = [
            ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            url,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30,
            )

            if process.returncode == 0 and stdout:
                import json
                return json.loads(stdout.decode())
            else:
                return None

        except (asyncio.TimeoutError, Exception):
            return None

    async def check_available(self) -> bool:
        """Check if ffmpeg/ffprobe is available."""
        ffmpeg_path = resolve_ffmpeg_path()
        if not ffmpeg_path:
            return False

        try:
            process = await asyncio.create_subprocess_exec(
                ffmpeg_path, "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            return process.returncode == 0
        except Exception:
            return False
