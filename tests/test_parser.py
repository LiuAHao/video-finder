"""Tests for parser module."""

import pytest
from app.services.parser import HLSParser, DASHParser, YtdlpParser, YtdlpFormat


class TestHLSParser:
    """Test HLS parser."""

    def setup_method(self):
        self.parser = HLSParser()

    def test_parse_master_playlist(self):
        """Test parsing master playlist."""
        content = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720
https://example.com/720p.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=4000000,RESOLUTION=1920x1080
https://example.com/1080p.m3u8
'''
        variants = self.parser._parse_master_playlist_content(content, "https://example.com/master.m3u8")
        assert len(variants) == 2
        assert variants[0].bandwidth == 2000000
        assert variants[0].resolution == "1280x720"
        assert variants[1].bandwidth == 4000000
        assert variants[1].resolution == "1920x1080"

    def test_parse_media_playlist(self):
        """Test parsing media playlist."""
        content = '''#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:10
#EXTINF:9.009,
segment0.ts
#EXTINF:9.009,
segment1.ts
#EXTINF:3.003,
segment2.ts
#EXT-X-ENDLIST
'''
        info = self.parser._parse_media_playlist_content(content, "https://example.com/playlist.m3u8")
        assert info["segments"] == 3
        assert info["duration"] == pytest.approx(21.021, rel=0.01)
        assert info["target_duration"] == 10

    def test_parse_attributes(self):
        """Test parsing EXT-X attributes."""
        line = 'BANDWIDTH=2000000,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"'
        attrs = self.parser._parse_attributes(line)
        assert attrs["BANDWIDTH"] == "2000000"
        assert attrs["RESOLUTION"] == "1280x720"
        assert attrs["CODECS"] == "avc1.64001f,mp4a.40.2"


class TestYtdlpParser:
    """Test yt-dlp parser."""

    def setup_method(self):
        self.parser = YtdlpParser()

    def test_parse_formats(self):
        """Test parsing yt-dlp formats."""
        data = {
            "formats": [
                {
                    "format_id": "137",
                    "ext": "mp4",
                    "resolution": "1920x1080",
                    "fps": 30,
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "filesize": 50000000,
                    "tbr": 2000,
                    "url": "https://example.com/video.mp4",
                },
                {
                    "format_id": "140",
                    "ext": "m4a",
                    "resolution": "audio only",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "filesize": 5000000,
                    "tbr": 128,
                    "url": "https://example.com/audio.m4a",
                },
            ]
        }

        formats = self.parser.parse_formats(data)
        assert len(formats) == 2
        assert formats[0].format_id == "137"
        assert formats[0].resolution == "1920x1080"

    def test_get_best_format(self):
        """Test getting best format."""
        formats = [
            YtdlpFormat("137", "mp4", "1920x1080", 30, "avc1", "none", 50000000, 2000),
            YtdlpFormat("136", "mp4", "1280x720", 30, "avc1", "none", 30000000, 1500),
            YtdlpFormat("140", "m4a", "audio only", None, "none", "mp4a", 5000000, 128),
        ]

        best = self.parser.get_best_format(formats)
        assert best.format_id == "137"

    def test_get_best_format_empty(self):
        """Test getting best format with empty list."""
        assert self.parser.get_best_format([]) is None
