"""Tests for progress module."""

import pytest
from app.services.progress import (
    ProgressInfo,
    ProgressTracker,
    YtdlpProgressParser,
    FFmpegProgressParser,
)


class TestProgressTracker:
    """Test ProgressTracker."""

    def setup_method(self):
        self.tracker = ProgressTracker()

    def test_update_creates_entry(self):
        info = self.tracker.update("task1", progress=50.0, status="downloading")
        assert info.progress == 50.0
        assert info.status == "downloading"

    def test_get_progress(self):
        self.tracker.update("task1", progress=30.0)
        info = self.tracker.get_progress("task1")
        assert info is not None
        assert info.progress == 30.0

    def test_get_progress_nonexistent(self):
        assert self.tracker.get_progress("nonexistent") is None

    def test_update_modifies_existing(self):
        self.tracker.update("task1", progress=10.0)
        self.tracker.update("task1", progress=80.0, speed="1.5MiB/s")
        info = self.tracker.get_progress("task1")
        assert info.progress == 80.0
        assert info.speed == "1.5MiB/s"

    def test_update_partial_fields(self):
        self.tracker.update("task1", progress=50.0, speed="1MiB/s", eta="00:30")
        self.tracker.update("task1", progress=75.0)
        info = self.tracker.get_progress("task1")
        assert info.progress == 75.0
        assert info.speed == "1MiB/s"
        assert info.eta == "00:30"

    def test_callback_notified(self):
        received = []
        self.tracker.add_callback("task1", lambda info: received.append(info))
        self.tracker.update("task1", progress=50.0)
        assert len(received) == 1
        assert received[0].progress == 50.0

    def test_multiple_callbacks(self):
        received_a = []
        received_b = []
        self.tracker.add_callback("task1", lambda info: received_a.append(info))
        self.tracker.add_callback("task1", lambda info: received_b.append(info))
        self.tracker.update("task1", progress=50.0)
        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_callback_exception_does_not_break(self):
        def bad_callback(info):
            raise RuntimeError("oops")

        self.tracker.add_callback("task1", bad_callback)
        # Should not raise
        self.tracker.update("task1", progress=50.0)

    def test_remove_task(self):
        self.tracker.update("task1", progress=50.0)
        self.tracker.remove_task("task1")
        assert self.tracker.get_progress("task1") is None

    def test_remove_task_cleans_callbacks(self):
        received = []
        self.tracker.add_callback("task1", lambda info: received.append(info))
        self.tracker.remove_task("task1")
        self.tracker.update("task1", progress=50.0)
        assert len(received) == 0


class TestYtdlpProgressParser:
    """Test YtdlpProgressParser."""

    def setup_method(self):
        self.parser = YtdlpProgressParser()

    def test_parse_progress_with_eta(self):
        line = "[download]  45.2% of ~150.00MiB at  1.50MiB/s ETA 01:30"
        info = self.parser.parse_line(line)
        assert info is not None
        assert info.progress == pytest.approx(45.2)
        assert info.speed == "1.50MiB/s"
        assert info.eta == "01:30"
        assert info.status == "downloading"

    def test_parse_progress_without_eta(self):
        line = "[download]  75.0% of ~200.00MiB at  2.00MiB/s"
        info = self.parser.parse_line(line)
        assert info is not None
        assert info.progress == pytest.approx(75.0)
        assert info.status == "downloading"

    def test_parse_progress_tilde_size(self):
        line = "[download]  10.5% of ~500.00MiB at  3.00MiB/s ETA 02:00"
        info = self.parser.parse_line(line)
        assert info is not None
        assert info.progress == pytest.approx(10.5)

    def test_parse_100_percent(self):
        line = "[download] 100% of 150.00MiB"
        info = self.parser.parse_line(line)
        assert info is not None
        assert info.progress == pytest.approx(100.0)
        assert info.status == "completed"

    def test_parse_merging(self):
        line = "[Merger] Merging formats into 'video.mp4'"
        info = self.parser.parse_line(line)
        assert info is not None
        assert info.progress == pytest.approx(99.0)
        assert info.status == "merging"

    def test_parse_irrelevant_line(self):
        line = "[youtube] Extracting URL: https://example.com"
        info = self.parser.parse_line(line)
        assert info is None

    def test_parse_empty_line(self):
        info = self.parser.parse_line("")
        assert info is None


class TestYtdlpParseSize:
    """Test YtdlpProgressParser._parse_size()."""

    def setup_method(self):
        self.parser = YtdlpProgressParser()

    def test_kib(self):
        assert self.parser._parse_size("100KiB") == 102400

    def test_mib(self):
        assert self.parser._parse_size("50.5MiB") == int(50.5 * 1024 * 1024)

    def test_gib(self):
        assert self.parser._parse_size("1.5GiB") == int(1.5 * 1024 * 1024 * 1024)

    def test_kb(self):
        assert self.parser._parse_size("100KB") == 100000

    def test_mb(self):
        assert self.parser._parse_size("50MB") == 50000000

    def test_gb(self):
        assert self.parser._parse_size("2GB") == 2000000000

    def test_raw_number(self):
        assert self.parser._parse_size("12345") == 12345

    def test_invalid(self):
        assert self.parser._parse_size("abc") is None


class TestFFmpegProgressParser:
    """Test FFmpegProgressParser."""

    def setup_method(self):
        self.parser = FFmpegProgressParser(total_duration=120.0)

    def test_parse_time_progress(self):
        line = "frame= 1000 fps= 30 q=28.0 size=   10240kB time=00:01:00.00 bitrate= 1400.0kbits/s speed=2.0x"
        info = self.parser.parse_line(line)
        assert info is not None
        assert info.progress == pytest.approx(50.0)
        assert info.speed == "2.0x"

    def test_parse_speed(self):
        line = "frame= 500 fps= 30 q=28.0 size=    5120kB time=00:00:30.00 bitrate= 1400.0kbits/s speed=1.5x"
        info = self.parser.parse_line(line)
        assert info is not None
        assert info.speed == "1.5x"

    def test_parse_no_time_returns_none(self):
        line = "frame= 100 fps= 30 q=28.0 size=    1024kB"
        info = self.parser.parse_line(line)
        assert info is None

    def test_parse_capped_at_100(self):
        parser = FFmpegProgressParser(total_duration=60.0)
        line = "frame= 2000 fps= 30 q=28.0 size=   20480kB time=00:02:00.00 bitrate= 1400.0kbits/s speed=2.0x"
        info = parser.parse_line(line)
        assert info is not None
        assert info.progress == pytest.approx(100.0)


class TestFFmpegParseTime:
    """Test FFmpegProgressParser._parse_time()."""

    def setup_method(self):
        self.parser = FFmpegProgressParser()

    def test_parse_time_simple(self):
        assert self.parser._parse_time("00:01:30.00") == 90.0

    def test_parse_time_hours(self):
        assert self.parser._parse_time("01:30:00.00") == 5400.0

    def test_parse_time_zero(self):
        assert self.parser._parse_time("00:00:00.00") == 0.0

    def test_parse_time_with_fraction(self):
        assert self.parser._parse_time("00:00:05.50") == pytest.approx(5.5)


class TestFFmpegHLSSegments:
    """Test FFmpegProgressParser HLS segment tracking."""

    def test_segment_tracking(self):
        parser = FFmpegProgressParser(total_segments=10, media_type="hls")
        line = "Opening 'https://cdn.example.com/hls/segment/00001.ts'"
        info = parser.parse_line(line)
        assert info is not None
        assert info.segment_current == 1
        assert info.segment_total == 10
        assert info.progress == pytest.approx(10.0)
        assert info.media_type == "hls"

    def test_multiple_segments(self):
        parser = FFmpegProgressParser(total_segments=4, media_type="hls")
        for i in range(1, 5):
            line = f"Opening 'https://cdn.example.com/hls/seg{i:05d}.ts'"
            info = parser.parse_line(line)
        assert info is not None
        assert info.segment_current == 4
        assert info.progress == pytest.approx(100.0)

    def test_non_hls_ignores_segments(self):
        parser = FFmpegProgressParser(total_segments=10)
        line = "Opening 'https://cdn.example.com/hls/segment/00001.ts'"
        info = parser.parse_line(line)
        assert info is None


class TestProgressInfo:
    """Test ProgressInfo defaults."""

    def test_default_values(self):
        info = ProgressInfo()
        assert info.progress == 0.0
        assert info.speed is None
        assert info.status == "running"
        assert info.logs == []

    def test_custom_values(self):
        info = ProgressInfo(
            progress=75.0,
            speed="2MiB/s",
            eta="00:10",
            downloaded_bytes=1024,
            total_bytes=2048,
            status="downloading",
        )
        assert info.progress == 75.0
        assert info.speed == "2MiB/s"
        assert info.eta == "00:10"
        assert info.downloaded_bytes == 1024
        assert info.total_bytes == 2048
