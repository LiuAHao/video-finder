"""Unit tests for sniffer URL heuristics."""

from app.services.sniffer import Sniffer


def test_request_heuristics_ignore_generic_download_endpoint():
    """A bare download endpoint should not be treated as a media URL from request path alone."""
    sniffer = Sniffer()
    assert sniffer._is_potential_video_url("https://example.com/download/file?id=123") is False


def test_request_heuristics_accept_real_media_urls():
    """Known media manifests and direct video URLs should still be detected."""
    sniffer = Sniffer()
    assert sniffer._is_potential_video_url("https://cdn.example.com/video/master.m3u8") is True
    assert sniffer._is_potential_video_url("https://cdn.example.com/video/episode-01.mp4?token=abc") is True


def test_hls_segment_detection_handles_ts_without_crashing():
    """HLS segment detection should classify .ts fragments without NameError."""
    assert Sniffer._is_hls_segment("https://cdn.example.com/hls/segment/00001.ts") is True
