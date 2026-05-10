"""Tests for the optimization changes: .ts filtering, episode scoring, path safety, protocol-relative URLs."""

import pytest
from app.services.extractor import HTMLExtractor, ExtractedResource
from app.services.sniffer import Sniffer
from app.services.safety import sanitize_output_name, build_safe_output_path
from app.schemas import MediaType, DiscoveryMethod


# ── Phase 1: .ts segment filtering ──────────────────────────────────────────

class TestTSSegmentFiltering:
    """HLS .ts segments must not appear in candidates."""

    def test_ts_segment_not_in_video_url(self):
        """_is_potential_video_url should reject .ts segment paths."""
        sniffer = Sniffer()
        assert sniffer._is_potential_video_url("https://cdn.example.com/hls/segment/00001.ts") is False

    def test_ts_segment_detected_by_is_hls_segment(self):
        assert Sniffer._is_hls_segment("https://cdn.example.com/hls/00001.ts") is True

    def test_m3u8_not_treated_as_segment(self):
        assert Sniffer._is_hls_segment("https://cdn.example.com/video/master.m3u8") is False

    def test_standalone_ts_not_segment(self):
        """A .ts file with a meaningful name should not be a segment."""
        assert Sniffer._is_hls_segment("https://cdn.example.com/full_movie.ts") is False


# ── Phase 2: Episode scoring (not hard filter) ──────────────────────────────

class TestEpisodeScoring:
    """Episode relevance should be a score penalty, not a hard filter."""

    def test_720p_not_detected_as_episode(self):
        """Resolution numbers should not be mistaken for episodes."""
        assert HTMLExtractor._extract_candidate_episode_hint(
            "https://cdn.example.com/video_720.mp4"
        ) is None

    def test_1080p_not_detected_as_episode(self):
        assert HTMLExtractor._extract_candidate_episode_hint(
            "https://cdn.example.com/source_1080.m3u8"
        ) is None

    def test_cdn_001_not_detected_as_episode(self):
        """Sequential CDN segment IDs should not be episodes."""
        assert HTMLExtractor._extract_candidate_episode_hint(
            "https://cdn.example.com/cdn_001.mp4"
        ) is None

    def test_strong_episode_pattern_still_works(self):
        """Explicit episode markers should still be detected."""
        assert HTMLExtractor._extract_candidate_episode_hint(
            "https://cdn.example.com/ep01.mp4"
        ) == 1
        assert HTMLExtractor._extract_candidate_episode_hint(
            "https://cdn.example.com/episode_12.mp4"
        ) == 12
        assert HTMLExtractor._extract_candidate_episode_hint(
            "https://cdn.example.com/第3集.mp4"
        ) == 3

    def test_irrelevant_candidate_gets_penalty_not_filtered(self):
        """A different-episode candidate should still appear, just scored lower."""
        extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")
        current = ExtractedResource(
            url="https://cdn.example.com/ep01.mp4",
            media_type=MediaType.DIRECT_VIDEO,
            discovery_method=DiscoveryMethod.NETWORK,
        )
        other = ExtractedResource(
            url="https://cdn.example.com/ep02.mp4",
            media_type=MediaType.DIRECT_VIDEO,
            discovery_method=DiscoveryMethod.NETWORK,
        )
        score_current = extractor.calculate_score(current)
        score_other = extractor.calculate_score(other)
        assert score_current > score_other
        # Penalty should be moderate (15 points), not lethal
        assert score_other > 0


# ── Phase 3: Output path safety ─────────────────────────────────────────────

class TestOutputPathSafety:
    """Download output paths must stay within download_dir."""

    def test_normal_filename(self):
        path = build_safe_output_path("/downloads", "my-video.mp4")
        assert str(path).startswith("/downloads")
        assert path.name == "my-video.mp4"

    def test_path_traversal_blocked(self):
        path = build_safe_output_path("/downloads", "../../etc/passwd")
        assert str(path).startswith("/downloads")
        assert ".." not in str(path)

    def test_absolute_path_blocked(self):
        path = build_safe_output_path("/downloads", "/tmp/out.mp4")
        assert str(path).startswith("/downloads")

    def test_sanitize_removes_illegal_chars(self):
        result = sanitize_output_name('video: test <1>.mp4')
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result

    def test_sanitize_strips_directory(self):
        result = sanitize_output_name("/some/path/video.mp4")
        assert "/" not in result
        assert result == "video.mp4"

    def test_empty_name_gets_default(self):
        path = build_safe_output_path("/downloads", "")
        assert path.name == "download"

    def test_dot_only_name_gets_default(self):
        path = build_safe_output_path("/downloads", "..")
        assert path.name == "download"

    def test_windows_style_absolute_path_is_sanitized(self):
        path = build_safe_output_path("/downloads", r"C:\tmp\out.mp4")
        assert str(path).startswith("/downloads")
        assert path.name == "out.mp4"


# ── Phase 4: Protocol-relative URL support ───────────────────────────────────

class TestProtocolRelativeURL:
    """Protocol-relative URLs (//cdn...) should be extracted."""

    def test_protocol_relative_in_json_config(self):
        extractor = HTMLExtractor("https://example.com")
        html = '''
        <html><body><script>
        var player = { src: "//cdn.example.com/video.m3u8" };
        </script></body></html>
        '''
        resources = extractor.extract_from_html(html)
        urls = [r.url for r in resources]
        assert any("cdn.example.com/video.m3u8" in u for u in urls)
        # Should be normalized to https://
        assert any(u.startswith("https://cdn.example.com") for u in urls)

    def test_protocol_relative_mp4(self):
        extractor = HTMLExtractor("https://example.com")
        html = '''
        <html><body><script>
        var config = { url: "//cdn.example.com/video.mp4" };
        </script></body></html>
        '''
        resources = extractor.extract_from_html(html)
        urls = [r.url for r in resources]
        assert any("cdn.example.com/video.mp4" in u for u in urls)

    def test_blob_url_still_excluded(self):
        extractor = HTMLExtractor("https://example.com")
        assert extractor._normalize_url("blob:https://example.com/abc") is None

    def test_data_url_still_excluded(self):
        extractor = HTMLExtractor("https://example.com")
        assert extractor._normalize_url("data:video/mp4;base64,AAA") is None

    def test_json_config_numeric_placeholder_not_extracted(self):
        extractor = HTMLExtractor("https://example.com/watch/1.html")
        html = '''
        <html><body><script>
        var config = { url: "1", src: "auto", file: "hd" };
        </script></body></html>
        '''
        resources = extractor.extract_from_html(html)
        assert resources == []
