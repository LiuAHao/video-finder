"""Tests for extractor module."""

import pytest
from app.services.extractor import HTMLExtractor, ExtractedResource
from app.schemas import MediaType, DiscoveryMethod


class TestHTMLExtractor:
    """Test HTML extraction."""

    def setup_method(self):
        self.extractor = HTMLExtractor("https://example.com")

    def test_extract_m3u8_from_html(self):
        """Test extracting m3u8 URLs from HTML."""
        html = '''
        <html>
        <body>
            <script>
                var player = {
                    src: "https://cdn.example.com/video/index.m3u8"
                };
            </script>
        </body>
        </html>
        '''
        resources = self.extractor.extract_from_html(html)
        assert len(resources) > 0
        assert any(r.url.endswith('.m3u8') for r in resources)

    def test_extract_mp4_from_video_tag(self):
        """Test extracting mp4 from video tag."""
        html = '''
        <html>
        <body>
            <video src="https://cdn.example.com/video.mp4"></video>
        </body>
        </html>
        '''
        resources = self.extractor.extract_from_html(html)
        assert len(resources) > 0
        assert any('.mp4' in r.url for r in resources)

    def test_extract_from_source_tag(self):
        """Test extracting from source tag."""
        html = '''
        <html>
        <body>
            <video>
                <source src="https://cdn.example.com/video.webm" type="video/webm">
            </video>
        </body>
        </html>
        '''
        resources = self.extractor.extract_from_html(html)
        assert len(resources) > 0

    def test_extract_from_data_attributes(self):
        """Test extracting from data attributes."""
        html = '''
        <html>
        <body>
            <div data-video-url="https://cdn.example.com/video.mp4"></div>
        </body>
        </html>
        '''
        resources = self.extractor.extract_from_html(html)
        assert len(resources) > 0

    def test_detect_media_type(self):
        """Test media type detection."""
        assert self.extractor._detect_media_type("https://example.com/video.m3u8") == MediaType.HLS
        assert self.extractor._detect_media_type("https://example.com/video.mpd") == MediaType.DASH
        assert self.extractor._detect_media_type("https://example.com/video.mp4") == MediaType.DIRECT_VIDEO
        assert self.extractor._detect_media_type("https://example.com/video.xyz") == MediaType.UNKNOWN

    def test_detect_temporary_url(self):
        """Test temporary URL detection."""
        assert self.extractor.detect_temporary_url("https://example.com/video.m3u8?token=abc123") is True
        assert self.extractor.detect_temporary_url("https://example.com/video.m3u8?expires=1234567890") is True
        assert self.extractor.detect_temporary_url("https://example.com/video.m3u8") is False

    def test_calculate_score(self):
        """Test score calculation."""
        hls_resource = ExtractedResource(
            url="https://example.com/master.m3u8",
            media_type=MediaType.HLS,
            discovery_method=DiscoveryMethod.NETWORK,
        )
        score = self.extractor.calculate_score(hls_resource)
        assert score > 0

        direct_resource = ExtractedResource(
            url="https://example.com/video.mp4",
            media_type=MediaType.DIRECT_VIDEO,
            discovery_method=DiscoveryMethod.HTML,
        )
        score = self.extractor.calculate_score(direct_resource)
        assert score > 0

    def test_normalize_url(self):
        """Test URL normalization."""
        # Absolute URL
        assert self.extractor._normalize_url("https://example.com/video.mp4") == "https://example.com/video.mp4"

        # Relative URL
        assert self.extractor._normalize_url("/video.mp4") == "https://example.com/video.mp4"

        # Protocol-relative URL
        assert self.extractor._normalize_url("//cdn.example.com/video.mp4") == "https://cdn.example.com/video.mp4"

        # Empty URL
        assert self.extractor._normalize_url("") is None

    def test_extract_from_json_config(self):
        """Test extraction from JSON config."""
        config = {
            "player": {
                "src": "https://example.com/video.m3u8",
                "autoplay": True
            }
        }
        resources = self.extractor._extract_from_json_config(config, None, set())
        assert len(resources) > 0

    def test_filter_non_media_urls_from_html_and_config(self):
        """Test that obvious non-media URLs are filtered out."""
        html = '''
        <html>
        <body>
            <script>
                var cfg = {
                    cover: "https://example.com/cover.jpg",
                    page: "https://example.com/watch/1.html",
                    player: {
                        url: "https://player.example.com/index.php?url=https://cdn.example.com/video.mp4"
                    },
                    video_url: "https://cdn.example.com/video.mp4"
                };
            </script>
        </body>
        </html>
        '''
        resources = self.extractor.extract_from_html(html)
        urls = [resource.url for resource in resources]
        assert "https://cdn.example.com/video.mp4" in urls
        assert "https://example.com/cover.jpg" not in urls
        assert "https://example.com/watch/1.html" not in urls
        assert "https://player.example.com/index.php?url=https://cdn.example.com/video.mp4" not in urls
