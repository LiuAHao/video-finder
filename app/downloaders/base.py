"""Base downloader interface."""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional, Callable
from pathlib import Path

from ..services.progress import ProgressInfo


class DownloadResult:
    """Download result."""

    def __init__(
        self,
        success: bool,
        output_path: Optional[str] = None,
        error_message: Optional[str] = None,
        file_size: Optional[int] = None,
    ):
        self.success = success
        self.output_path = output_path
        self.error_message = error_message
        self.file_size = file_size


class BaseDownloader(ABC):
    """Base downloader interface."""

    def __init__(
        self,
        url: str,
        output_path: str,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        on_progress: Optional[Callable[[ProgressInfo], None]] = None,
    ):
        self.url = url
        self.output_path = output_path
        self.referer = referer
        self.user_agent = user_agent
        self.on_progress = on_progress
        self._cancelled = False
        self._process: Optional[asyncio.subprocess.Process] = None

    @abstractmethod
    async def download(self) -> DownloadResult:
        """Start download and return result."""
        pass

    @abstractmethod
    async def cancel(self) -> None:
        """Cancel the download."""
        pass

    @abstractmethod
    def get_command(self) -> list[str]:
        """Get the download command."""
        pass

    def _report_progress(self, info: ProgressInfo) -> None:
        """Report progress to callback."""
        if self.on_progress:
            self.on_progress(info)

    def _ensure_output_dir(self) -> None:
        """Ensure output directory exists."""
        output_dir = Path(self.output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

    async def _run_process(self, command: list[str]) -> DownloadResult:
        """Run a subprocess and capture output."""
        self._ensure_output_dir()
        start_time = time.time()

        try:
            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await self._process.communicate()

            if self._cancelled:
                return DownloadResult(
                    success=False,
                    error_message="Download cancelled",
                )

            if self._process.returncode == 0:
                output_path = Path(self.output_path)
                # Only accept files modified after download started
                if output_path.exists() and output_path.stat().st_mtime >= start_time:
                    file_size = output_path.stat().st_size
                else:
                    resolved = self._resolve_output_path(output_path, after_time=start_time)
                    file_size = resolved.stat().st_size if resolved and resolved.exists() else None
                    output_path = resolved or output_path

                return DownloadResult(
                    success=True,
                    output_path=str(output_path),
                    file_size=file_size,
                )
            else:
                error = stderr.decode() if stderr else "Unknown error"
                return DownloadResult(
                    success=False,
                    error_message=error,
                )

        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=str(e),
            )

    async def _run_process_with_progress(
        self, command: list[str], parser: Callable[[str], Optional[ProgressInfo]]
    ) -> DownloadResult:
        """Run a subprocess with progress parsing."""
        self._ensure_output_dir()
        output_path = Path(self.output_path)
        stderr_tail: list[str] = []
        start_time = time.time()

        try:
            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def read_stream(stream: asyncio.StreamReader | None) -> None:
                if stream is None:
                    return
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line_str = line.decode(errors="replace").strip()
                    if line_str:
                        stderr_tail.append(line_str)
                        del stderr_tail[:-20]
                    progress_info = parser(line_str)
                    if progress_info:
                        self._report_progress(progress_info)

            stdout_task = asyncio.create_task(read_stream(self._process.stdout))
            stderr_task = asyncio.create_task(read_stream(self._process.stderr))

            while self._process.returncode is None:
                if self._cancelled:
                    self._process.terminate()
                    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                    return DownloadResult(
                        success=False,
                        error_message="Download cancelled",
                    )
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=0.2)
                except asyncio.TimeoutError:
                    continue

            # Wait for process to complete
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

            if self._process.returncode == 0:
                resolved_output_path = self._resolve_output_path(output_path, after_time=start_time)
                file_size = (
                    resolved_output_path.stat().st_size
                    if resolved_output_path and resolved_output_path.exists()
                    else None
                )

                self._report_progress(ProgressInfo(
                    progress=100.0,
                    status="completed",
                ))

                return DownloadResult(
                    success=True,
                    output_path=str(resolved_output_path or output_path),
                    file_size=file_size,
                )
            else:
                error = "\n".join(stderr_tail[-8:]) or f"Process exited with code {self._process.returncode}"
                return DownloadResult(
                    success=False,
                    error_message=error,
                )

        except Exception as e:
            return DownloadResult(
                success=False,
                error_message=str(e),
            )

    def _resolve_output_path(self, output_path: Path, after_time: Optional[float] = None) -> Optional[Path]:
        """Resolve downloader output when the tool replaces the extension.

        Args:
            output_path: Expected output path.
            after_time: Unix timestamp. If provided, only consider files modified after this time.
        """
        if output_path.exists():
            if after_time and output_path.stat().st_mtime < after_time:
                return None
            return output_path

        parent = output_path.parent
        if not parent.exists():
            return None

        matches = [
            path for path in parent.glob(f"{output_path.stem}.*")
            if path.is_file() and not path.name.endswith((".part", ".ytdl", ".tmp"))
        ]
        if after_time:
            matches = [p for p in matches if p.stat().st_mtime >= after_time]
        if not matches:
            return None

        return max(matches, key=lambda path: path.stat().st_mtime)
