"""yt-dlp downloader implementation."""

import asyncio
import shutil
from typing import Optional, Callable
from pathlib import Path

from .base import BaseDownloader, DownloadResult
from ..services.progress import ProgressInfo, YtdlpProgressParser


class YtdlpDownloader(BaseDownloader):
    """yt-dlp downloader."""

    def __init__(
        self,
        url: str,
        output_path: str,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        on_progress: Optional[Callable[[ProgressInfo], None]] = None,
        format_spec: Optional[str] = None,
        concurrency: int = 8,
        extra_args: Optional[list[str]] = None,
    ):
        super().__init__(url, output_path, referer, user_agent, on_progress)
        self.format_spec = format_spec
        self.concurrency = concurrency
        self.extra_args = extra_args or []
        self._parser = YtdlpProgressParser()

    def get_command(self) -> list[str]:
        """Get yt-dlp command."""
        # Find yt-dlp executable
        ytdlp_path = shutil.which("yt-dlp")
        if not ytdlp_path:
            raise FileNotFoundError("yt-dlp not found. Please install yt-dlp.")

        cmd = [
            ytdlp_path,
            "--newline",  # Output progress on new lines
            "--no-colors",  # No color codes
            "--continue",  # Resume partially downloaded files
            "--concurrent-fragments", str(self.concurrency),
            "--merge-output-format", "mp4",
            "--legacy-server-connect",  # Fix SSL handshake errors on some servers
            "--no-check-certificates",  # Skip certificate verification
            "--geo-bypass",  # Bypass geographic restrictions
            "--no-warnings",
        ]

        # Format specification
        if self.format_spec:
            cmd.extend(["-f", self.format_spec])
        else:
            # Flexible format selection: best video+audio, fallback to best single stream
            cmd.extend(["-f", "bestvideo*+bestaudio/bestvideo+bestaudio/best"])

        # Output template
        output_dir = Path(self.output_path).parent
        output_name = Path(self.output_path).stem
        cmd.extend([
            "-o", str(Path(output_dir) / f"{output_name}.%(ext)s"),
        ])

        # Referer
        if self.referer:
            cmd.extend(["--referer", self.referer])

        # User-Agent
        if self.user_agent:
            cmd.extend(["--user-agent", self.user_agent])

        # Extra args
        cmd.extend(self.extra_args)

        # URL
        cmd.append(self.url)

        return cmd

    async def download(self) -> DownloadResult:
        """Start yt-dlp download."""
        try:
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
                error_message=f"yt-dlp error: {e}",
            )

    async def cancel(self) -> None:
        """Cancel the download."""
        self._cancelled = True
        await self._terminate_process()

    def _parse_progress(self, line: str) -> Optional[ProgressInfo]:
        """Parse yt-dlp progress line."""
        return self._parser.parse_line(line)


class YtdlpProbe:
    """Probe page using yt-dlp to get video info."""

    def __init__(
        self,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        self.referer = referer
        self.user_agent = user_agent

    async def probe(self, url: str) -> Optional[dict]:
        """Probe URL and return video info."""
        ytdlp_path = shutil.which("yt-dlp")
        if not ytdlp_path:
            return None

        cmd = [
            ytdlp_path,
            "--dump-json",
            "--no-download",
            "--no-warnings",
            "--legacy-server-connect",
            "--no-check-certificates",
            "--geo-bypass",
        ]

        if self.referer:
            cmd.extend(["--referer", self.referer])

        if self.user_agent:
            cmd.extend(["--user-agent", self.user_agent])

        cmd.append(url)

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
        """Check if yt-dlp is available."""
        ytdlp_path = shutil.which("yt-dlp")
        if not ytdlp_path:
            return False

        try:
            process = await asyncio.create_subprocess_exec(
                ytdlp_path, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            return process.returncode == 0
        except Exception:
            return False
