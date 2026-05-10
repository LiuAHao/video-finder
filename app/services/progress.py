"""Progress tracking and reporting."""

import asyncio
import re
from typing import Optional, Callable, AsyncGenerator
from datetime import datetime


class ProgressInfo:
    """Progress information."""

    def __init__(
        self,
        progress: float = 0.0,
        speed: Optional[str] = None,
        eta: Optional[str] = None,
        downloaded_bytes: Optional[int] = None,
        total_bytes: Optional[int] = None,
        status: str = "running",
        message: Optional[str] = None,
        media_type: Optional[str] = None,
        segment_current: Optional[int] = None,
        segment_total: Optional[int] = None,
        stage: Optional[str] = None,
        elapsed_seconds: Optional[int] = None,
        file_size_bytes: Optional[int] = None,
        logs: Optional[list[str]] = None,
    ):
        self.progress = progress
        self.speed = speed
        self.eta = eta
        self.downloaded_bytes = downloaded_bytes
        self.total_bytes = total_bytes
        self.status = status
        self.message = message
        self.media_type = media_type
        self.segment_current = segment_current
        self.segment_total = segment_total
        self.stage = stage
        self.elapsed_seconds = elapsed_seconds
        self.file_size_bytes = file_size_bytes
        self.logs = logs or []
        self.timestamp = datetime.utcnow()


class ProgressTracker:
    """Track and report download progress."""

    def __init__(self):
        self._progress: dict[str, ProgressInfo] = {}
        self._callbacks: dict[str, list[Callable]] = {}

    def update(
        self,
        task_id: str,
        progress: Optional[float] = None,
        speed: Optional[str] = None,
        eta: Optional[str] = None,
        downloaded_bytes: Optional[int] = None,
        total_bytes: Optional[int] = None,
        status: Optional[str] = None,
        message: Optional[str] = None,
        stage: Optional[str] = None,
        elapsed_seconds: Optional[int] = None,
        file_size_bytes: Optional[int] = None,
        logs: Optional[list[str]] = None,
    ) -> ProgressInfo:
        """Update progress for a task."""
        if task_id not in self._progress:
            self._progress[task_id] = ProgressInfo()

        info = self._progress[task_id]

        if progress is not None:
            info.progress = progress
        if speed is not None:
            info.speed = speed
        if eta is not None:
            info.eta = eta
        if downloaded_bytes is not None:
            info.downloaded_bytes = downloaded_bytes
        if total_bytes is not None:
            info.total_bytes = total_bytes
        if status is not None:
            info.status = status
        if message is not None:
            info.message = message
        if stage is not None:
            info.stage = stage
        if elapsed_seconds is not None:
            info.elapsed_seconds = elapsed_seconds
        if file_size_bytes is not None:
            info.file_size_bytes = file_size_bytes
        if logs is not None:
            info.logs = logs

        info.timestamp = datetime.utcnow()

        # Notify callbacks
        self._notify_callbacks(task_id, info)

        return info

    def get_progress(self, task_id: str) -> Optional[ProgressInfo]:
        """Get progress for a task."""
        return self._progress.get(task_id)

    def add_callback(self, task_id: str, callback: Callable) -> None:
        """Add callback for progress updates."""
        if task_id not in self._callbacks:
            self._callbacks[task_id] = []
        self._callbacks[task_id].append(callback)

    def _notify_callbacks(self, task_id: str, info: ProgressInfo) -> None:
        """Notify registered callbacks."""
        for callback in self._callbacks.get(task_id, []):
            try:
                callback(info)
            except Exception:
                pass

    def remove_task(self, task_id: str) -> None:
        """Remove task progress."""
        self._progress.pop(task_id, None)
        self._callbacks.pop(task_id, None)


class YtdlpProgressParser:
    """Parse yt-dlp progress output."""

    # yt-dlp progress patterns
    _progress_pattern = re.compile(
        r'\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+\s*\w+)\s+at\s+([\d.]+\s*\w+/s)\s+ETA\s+(\d+(?::\d+)+)'
    )
    _progress_pattern2 = re.compile(
        r'\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+\s*\w+)'
    )
    _complete_pattern = re.compile(
        r'\[download\]\s+100%\s+of\s+([\d.]+\w+)'
    )
    _merging_pattern = re.compile(
        r'\[Merger\]'
    )

    def parse_line(self, line: str) -> Optional[ProgressInfo]:
        """Parse a line of yt-dlp output."""
        line = line.strip()

        # Check for progress
        match = self._progress_pattern.search(line)
        if match:
            return ProgressInfo(
                progress=float(match.group(1)),
                total_bytes=self._parse_size(match.group(2).replace(" ", "")),
                speed=match.group(3).replace(" ", ""),
                eta=match.group(4),
                status="downloading",
            )

        # Check for completion before the looser progress pattern.
        match = self._complete_pattern.search(line)
        if match:
            return ProgressInfo(
                progress=100.0,
                total_bytes=self._parse_size(match.group(1)),
                status="completed",
            )

        # Check for progress without ETA
        match = self._progress_pattern2.search(line)
        if match:
            return ProgressInfo(
                progress=float(match.group(1)),
                speed=match.group(2),
                status="downloading",
            )

        # Check for merging
        if self._merging_pattern.search(line):
            return ProgressInfo(
                progress=99.0,
                status="merging",
                message="Merging video and audio...",
            )

        return None

    def _parse_size(self, size_str: str) -> Optional[int]:
        """Parse size string to bytes."""
        try:
            size_str = size_str.strip()
            if size_str.endswith("KiB"):
                return int(float(size_str[:-3]) * 1024)
            elif size_str.endswith("MiB"):
                return int(float(size_str[:-3]) * 1024 * 1024)
            elif size_str.endswith("GiB"):
                return int(float(size_str[:-3]) * 1024 * 1024 * 1024)
            elif size_str.endswith("KB"):
                return int(float(size_str[:-2]) * 1000)
            elif size_str.endswith("MB"):
                return int(float(size_str[:-2]) * 1000 * 1000)
            elif size_str.endswith("GB"):
                return int(float(size_str[:-2]) * 1000 * 1000 * 1000)
            else:
                return int(float(size_str))
        except (ValueError, TypeError):
            return None


class FFmpegProgressParser:
    """Parse ffmpeg progress output."""

    # ffmpeg progress patterns
    _time_pattern = re.compile(
        r'time=(\d+:\d+:\d+\.\d+)'
    )
    _speed_pattern = re.compile(
        r'speed=\s*([\d.]+)x'
    )
    _size_pattern = re.compile(
        r'size=\s*(\d+)(\w+)'
    )
    _segment_pattern = re.compile(
        r"Opening '.*\.ts\??"
    )

    def __init__(
        self,
        total_duration: Optional[float] = None,
        total_segments: Optional[int] = None,
        media_type: Optional[str] = None,
    ):
        self.total_duration = total_duration
        self.total_segments = total_segments
        self.media_type = media_type
        self._segment_current = 0

    def parse_line(self, line: str) -> Optional[ProgressInfo]:
        """Parse a line of ffmpeg output."""
        line = line.strip()

        # Track HLS segment progress
        if self.media_type == "hls" and self._segment_pattern.search(line):
            self._segment_current += 1
            progress = 0.0
            if self.total_segments and self.total_segments > 0:
                progress = min(100.0, (self._segment_current / self.total_segments) * 100)
            return ProgressInfo(
                progress=progress,
                status="downloading",
                media_type="hls",
                segment_current=self._segment_current,
                segment_total=self.total_segments,
            )

        # Check for time
        time_match = self._time_pattern.search(line)
        if not time_match:
            return None

        time_str = time_match.group(1)
        current_time = self._parse_time(time_str)

        # Calculate progress if total duration is known
        progress = 0.0
        if self.total_duration and self.total_duration > 0:
            progress = min(100.0, (current_time / self.total_duration) * 100)

        # Get speed
        speed = None
        speed_match = self._speed_pattern.search(line)
        if speed_match:
            speed = f"{speed_match.group(1)}x"

        # Get size
        total_bytes = None
        size_match = self._size_pattern.search(line)
        if size_match:
            size = int(size_match.group(1))
            unit = size_match.group(2).upper()
            if unit == "KB":
                size *= 1000
            elif unit == "MB":
                size *= 1000 * 1000
            elif unit == "GB":
                size *= 1000 * 1000 * 1000
            total_bytes = size

        result = ProgressInfo(
            progress=progress,
            speed=speed,
            total_bytes=total_bytes,
            status="downloading",
        )
        # Preserve segment info for HLS
        if self.media_type == "hls":
            result.media_type = "hls"
            result.segment_current = self._segment_current
            result.segment_total = self.total_segments
        return result

    def _parse_time(self, time_str: str) -> float:
        """Parse time string to seconds."""
        try:
            parts = time_str.split(":")
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            return 0.0


async def parse_m3u8_segments(url: str) -> Optional[int]:
    """Parse m3u8 URL and return total segment count."""
    import asyncio
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-sL", "-m", "10", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode != 0:
            return None
        content = stdout.decode("utf-8", errors="ignore")
        count = sum(1 for line in content.splitlines() if line.strip().endswith(".ts") or ".ts?" in line)
        return count if count > 0 else None
    except Exception:
        return None


class SSEProgressStreamer:
    """Stream progress updates via SSE."""

    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}

    async def subscribe(self, task_id: str) -> AsyncGenerator[str, None]:
        """Subscribe to progress updates for a task."""
        if task_id not in self._queues:
            self._queues[task_id] = asyncio.Queue()

        queue = self._queues[task_id]

        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            self._queues.pop(task_id, None)

    async def publish(self, task_id: str, data: str) -> None:
        """Publish progress update for a task."""
        if task_id not in self._queues:
            self._queues[task_id] = asyncio.Queue()

        await self._queues[task_id].put(data)
