"""Tests for downloader module."""

import pytest
from unittest.mock import AsyncMock, patch
from app.downloaders.ytdlp import YtdlpDownloader
from app.downloaders.ffmpeg import FFmpegDownloader
from app.downloaders.http import HttpDownloader
from app.schemas import MediaType


class TestYtdlpDownloader:
    """Test yt-dlp downloader."""

    def test_get_command(self):
        """Test command generation."""
        downloader = YtdlpDownloader(
            url="https://example.com/video.m3u8",
            output_path="/tmp/video.mp4",
            referer="https://example.com",
            user_agent="TestAgent",
        )

        with patch('shutil.which', return_value='/usr/local/bin/yt-dlp'):
            cmd = downloader.get_command()

        assert '/usr/local/bin/yt-dlp' in cmd
        assert '--newline' in cmd
        assert '--referer' in cmd
        assert 'https://example.com' in cmd
        assert '--user-agent' in cmd
        assert 'TestAgent' in cmd
        assert 'https://example.com/video.m3u8' in cmd

    def test_get_command_not_found(self):
        """Test command when yt-dlp not found."""
        downloader = YtdlpDownloader(
            url="https://example.com/video.m3u8",
            output_path="/tmp/video.mp4",
        )

        with patch('shutil.which', return_value=None):
            with pytest.raises(FileNotFoundError):
                downloader.get_command()


class TestFFmpegDownloader:
    """Test ffmpeg downloader."""

    def test_get_command(self):
        """Test command generation."""
        downloader = FFmpegDownloader(
            url="https://example.com/video.m3u8",
            output_path="/tmp/video.mp4",
            referer="https://example.com",
            user_agent="TestAgent",
        )

        with patch('shutil.which', return_value='/usr/local/bin/ffmpeg'):
            cmd = downloader.get_command()

        assert '/usr/local/bin/ffmpeg' in cmd
        assert '-y' in cmd
        assert '-c' in cmd
        assert 'copy' in cmd
        assert 'https://example.com/video.m3u8' in cmd
        assert '/tmp/video.mp4' in cmd

    def test_get_command_not_found(self):
        """Test command when ffmpeg not found."""
        downloader = FFmpegDownloader(
            url="https://example.com/video.m3u8",
            output_path="/tmp/video.mp4",
        )

        with patch('shutil.which', return_value=None):
            with pytest.raises(FileNotFoundError):
                downloader.get_command()


class TestHttpDownloader:
    """Test HTTP downloader."""

    def test_get_filename_from_url(self):
        """Test filename extraction from URL."""
        assert HttpDownloader.get_filename_from_url("https://example.com/video.mp4") == "video.mp4"
        assert HttpDownloader.get_filename_from_url("https://example.com/path/video.webm") == "video.webm"
        assert HttpDownloader.get_filename_from_url("https://example.com/noext") == "download"
