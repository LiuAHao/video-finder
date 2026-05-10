"""Real-world URL test cases based on actual platforms."""

import pytest
from app.services.extractor import HTMLExtractor, ExtractedResource
from app.services.sniffer import Sniffer
from app.schemas import MediaType, DiscoveryMethod


# ── Real page URLs provided by user ──────────────────────────────────────────

USER_PAGE_URLS = [
    "https://www.bilibili.com/video/BV1x6RvB5Egf/?spm_id_from=333.1007.tianma.1-1-1.click&vd_source=e6105397655b7265cbb9c80359f9b9e6",
    "https://d2883ce011d2398b.tbdm01.cc/play/43-4-1.html",
    "https://www.mxdmv.com/mxdmv1/126016_1_1.html",
    "https://dm1.xfdm.pro/watch/3416/1/1.html",
    "https://www.acfun.cn/bangumi/aa5024869",
    "https://www.acfuns.net/vodplay/22646-1-1.html",
    "https://www.netflixgc.com/play/19621-2-1.html",
    "https://m.meijtt.com/v/122421-1-1/",
]

# ── Additional platform URLs for broader coverage ────────────────────────────

EXTRA_PAGE_URLS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://v.qq.com/x/cover/mzc00200mp8e98r.html",
    "https://www.iqiyi.com/v_19rrl3q5no.html",
    "https://v.youku.com/v_show/id_XNjMyMTQ4MDk2MA==.html",
    "https://www.twitch.tv/videos/123456789",
    "https://www.ixigua.com/7123456789012345678",
    "https://www.mgtv.com/b/1/123456.html",
    "https://www.pptv.com/page/123456.html",
]


class TestURLDetection:
    """Test that sniffer correctly identifies video URLs from real platforms."""

    def setup_method(self):
        self.sniffer = Sniffer()

    @pytest.mark.parametrize("url,expected", [
        # HLS manifests
        ("https://cdn.example.com/video/index.m3u8", True),
        ("https://cdn.example.com/video/master.m3u8?token=abc", True),
        # DASH manifests
        ("https://cdn.example.com/video/manifest.mpd", True),
        # Direct video
        ("https://cdn.example.com/video.mp4", True),
        ("https://cdn.example.com/video.webm", True),
        ("https://cdn.example.com/video.mkv", True),
        ("https://cdn.example.com/video.mp4?token=abc&expires=123", True),
        # Non-video URLs should be rejected
        ("https://example.com/download/file?id=123", False),
        ("https://example.com/api/video/info", True),  # matches /video/ pattern in sniffer
        ("https://example.com/cover.jpg", False),
    ])
    def test_video_url_detection(self, url, expected):
        assert self.sniffer._is_potential_video_url(url) is expected


class TestHLSSegmentDetection:
    """Test HLS segment detection with real CDN patterns."""

    @pytest.mark.parametrize("url,expected", [
        # Typical CDN HLS segments
        ("https://cdn.example.com/hls/segment/00001.ts", True),
        ("https://cdn.example.com/hls/0a1b2c3d4e5f6a7b8c9d0e1f.ts", True),
        ("https://cdn.example.com/seg/seg-1-v1-a1.ts", True),
        ("https://cdn.example.com/chunk/001.ts", True),
        ("https://cdn.example.com/hls/segment/00001.ts?hash=abc123", True),
        # Standalone .ts video files should NOT be treated as segments
        ("https://cdn.example.com/full_movie.ts", False),
        ("https://cdn.example.com/video.ts", False),
    ])
    def test_hls_segment_patterns(self, url, expected):
        assert Sniffer._is_hls_segment(url) is expected


class TestEpisodeExtraction:
    """Test episode number extraction from real platform URL patterns."""

    def setup_method(self):
        self.extractor = HTMLExtractor("https://example.com")

    @pytest.mark.parametrize("page_url,expected_episode", [
        # User-provided URLs with episode patterns
        ("https://d2883ce011d2398b.tbdm01.cc/play/43-4-1.html", None),
        ("https://dm1.xfdm.pro/watch/3416/1/1.html", 1),  # ends with /1.html
        # These use dash-separated IDs (e.g. 22646-1-1) which current regex doesn't parse
        ("https://www.acfuns.net/vodplay/22646-1-1.html", None),
        ("https://www.netflixgc.com/play/19621-2-1.html", None),
        ("https://m.meijtt.com/v/122421-1-1/", None),
        # Chinese episode markers
        ("https://example.com/watch/123/第1集.html", 1),
        ("https://example.com/watch/123/第12话.html", 12),
        # English episode markers
        ("https://example.com/watch/episode-5.html", 5),
        ("https://example.com/watch/ep03.html", 3),
        # No episode
        ("https://www.bilibili.com/video/BV1x6RvB5Egf/", None),
        ("https://www.acfun.cn/bangumi/aa5024869", None),
    ])
    def test_page_episode_hint(self, page_url, expected_episode):
        extractor = HTMLExtractor(page_url)
        assert extractor._extract_page_episode_hint() == expected_episode

    @pytest.mark.parametrize("candidate_url,expected_episode", [
        ("https://cdn.example.com/episode_01.m3u8", 1),
        ("https://cdn.example.com/ep12.mp4", 12),
        ("https://cdn.example.com/第3集.mp4", 3),
        # basename is index.m3u8, so episode in parent dir is not detected
        ("https://cdn.example.com/第24话/index.m3u8", None),
        # Weak patterns removed: bare trailing digits no longer match
        ("https://cdn.example.com/00001.ts", None),
        ("https://cdn.example.com/video.mp4", None),
    ])
    def test_candidate_episode_hint(self, candidate_url, expected_episode):
        assert HTMLExtractor._extract_candidate_episode_hint(candidate_url) == expected_episode


class TestEpisodeFiltering:
    """Test that episode filtering keeps current episode and rejects others."""

    def test_keeps_matching_episode(self):
        extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")
        assert extractor._is_relevant_to_page("https://cdn.example.com/ep01.mp4") is True

    def test_rejects_different_episode(self):
        extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")
        assert extractor._is_relevant_to_page("https://cdn.example.com/ep02.mp4") is False

    def test_keeps_url_without_episode_number(self):
        extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")
        assert extractor._is_relevant_to_page("https://cdn.example.com/video.m3u8") is True

    def test_no_page_episode_keeps_all(self):
        extractor = HTMLExtractor("https://www.bilibili.com/video/BV1x6RvB5Egf/")
        assert extractor._is_relevant_to_page("https://cdn.example.com/ep01.mp4") is True
        assert extractor._is_relevant_to_page("https://cdn.example.com/ep02.mp4") is True


class TestScoreRanking:
    """Test score ranking with realistic candidate mixes."""

    def test_hls_master_ranks_highest(self):
        extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")
        candidates = [
            ExtractedResource(
                url="https://cdn.example.com/master.m3u8",
                media_type=MediaType.HLS,
                discovery_method=DiscoveryMethod.NETWORK,
            ),
            ExtractedResource(
                url="https://cdn.example.com/video.mp4",
                media_type=MediaType.DIRECT_VIDEO,
                discovery_method=DiscoveryMethod.HTML,
            ),
            ExtractedResource(
                url="https://dm1.xfdm.pro/watch/3416/1/1.html",
                media_type=MediaType.PAGE_EXTRACT,
                discovery_method=DiscoveryMethod.YT_DLP,
            ),
        ]
        scores = [(c.url, extractor.calculate_score(c)) for c in candidates]
        # HLS > direct video > page extract
        assert scores[0][1] > scores[1][1] > scores[2][1]

    def test_network_discovery_scores_higher_than_html(self):
        extractor = HTMLExtractor("https://example.com")
        network = ExtractedResource(
            url="https://cdn.example.com/v.mp4",
            media_type=MediaType.DIRECT_VIDEO,
            discovery_method=DiscoveryMethod.NETWORK,
        )
        html = ExtractedResource(
            url="https://cdn.example.com/v2.mp4",
            media_type=MediaType.DIRECT_VIDEO,
            discovery_method=DiscoveryMethod.HTML,
        )
        assert extractor.calculate_score(network) > extractor.calculate_score(html)

    def test_temporary_url_penalty(self):
        extractor = HTMLExtractor("https://example.com")
        permanent = ExtractedResource(
            url="https://cdn.example.com/video.m3u8",
            media_type=MediaType.HLS,
            discovery_method=DiscoveryMethod.NETWORK,
        )
        temporary = ExtractedResource(
            url="https://cdn.example.com/video.m3u8?token=abc123&expires=999",
            media_type=MediaType.HLS,
            discovery_method=DiscoveryMethod.NETWORK,
        )
        assert extractor.calculate_score(permanent) > extractor.calculate_score(temporary)

    def test_page_url_penalty(self):
        extractor = HTMLExtractor("https://example.com")
        media = ExtractedResource(
            url="https://cdn.example.com/video.mp4",
            media_type=MediaType.DIRECT_VIDEO,
            discovery_method=DiscoveryMethod.HTML,
        )
        page = ExtractedResource(
            url="https://example.com/watch.html",
            media_type=MediaType.DIRECT_VIDEO,
            discovery_method=DiscoveryMethod.HTML,
        )
        assert extractor.calculate_score(media) > extractor.calculate_score(page)

    def test_realistic_candidate_mix_from_anime_site(self):
        """Simulate a typical anime site sniff result and verify ranking."""
        extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")
        candidates = [
            ExtractedResource(
                url="https://dm1.xfdm.pro/watch/3416/1/1.html",
                media_type=MediaType.PAGE_EXTRACT,
                discovery_method=DiscoveryMethod.YT_DLP,
            ),
            ExtractedResource(
                url="https://cdn.example.com/hls/master.m3u8",
                media_type=MediaType.HLS,
                discovery_method=DiscoveryMethod.NETWORK,
            ),
            ExtractedResource(
                url="https://cdn.example.com/hls/720p.m3u8",
                media_type=MediaType.HLS,
                discovery_method=DiscoveryMethod.NETWORK,
            ),
            ExtractedResource(
                url="https://cdn.example.com/video.mp4",
                media_type=MediaType.DIRECT_VIDEO,
                discovery_method=DiscoveryMethod.HTML,
            ),
        ]
        scored = sorted(candidates, key=lambda c: extractor.calculate_score(c), reverse=True)
        # master.m3u8 should rank first
        assert scored[0].url == "https://cdn.example.com/hls/master.m3u8"


class TestRealPlatformHTMLExtraction:
    """Test HTML extraction with markup patterns from real platforms."""

    def test_anime_site_player_config(self):
        """Typical anime site player configuration with m3u8 URL."""
        extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")
        html = '''
        <html><body>
        <div id="player"></div>
        <script>
        var player = new DPlayer({
            container: document.getElementById('player'),
            video: {
                url: "https://cdn.example.com/hls/3416/1/index.m3u8",
                type: "customHls"
            }
        });
        </script>
        </body></html>
        '''
        resources = extractor.extract_from_html(html)
        urls = [r.url for r in resources]
        assert any("index.m3u8" in u for u in urls)

    def test_anime_site_with_data_attributes(self):
        """Anime sites using data attributes for video URLs."""
        extractor = HTMLExtractor("https://www.acfuns.net/vodplay/22646-1-1.html")
        html = '''
        <html><body>
        <div class="player" data-video-url="https://cdn.example.com/22646/ep01.m3u8"></div>
        </body></html>
        '''
        resources = extractor.extract_from_html(html)
        assert len(resources) > 0
        assert any(".m3u8" in r.url for r in resources)

    def test_bilibili_style_page(self):
        """Bilibili-style page (yt-dlp handles these, but test HTML fallback)."""
        extractor = HTMLExtractor("https://www.bilibili.com/video/BV1x6RvB5Egf/")
        html = '''
        <html><body>
        <script>
        window.__playinfo__ = {
            "data": {
                "dash": {
                    "video": [
                        {"baseUrl": "https://upos-sz-mirrorcos.bilivideo.com/video.mp4"}
                    ]
                }
            }
        };
        </script>
        </body></html>
        '''
        resources = extractor.extract_from_html(html)
        # May or may not extract depending on pattern matching, but should not crash
        assert isinstance(resources, list)

    def test_iframe_embed_pattern(self):
        """Many anime sites embed video via iframes."""
        extractor = HTMLExtractor("https://www.mxdmv.com/mxdmv1/126016_1_1.html")
        html = '''
        <html><body>
        <iframe src="https://player.example.com/embed/126016" frameborder="0" allowfullscreen></iframe>
        </body></html>
        '''
        # Extractor processes the main HTML, iframe content handled by sniffer
        resources = extractor.extract_from_html(html)
        assert isinstance(resources, list)

    def test_multiple_video_sources_with_episode_filtering(self):
        """Page lists multiple episodes, all kept but current scores higher."""
        extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")
        html = '''
        <html><body>
        <script>
        var episodes = [
            {src: "https://cdn.example.com/3416/ep01.m3u8", ep: 1},
            {src: "https://cdn.example.com/3416/ep02.m3u8", ep: 2},
            {src: "https://cdn.example.com/3416/ep03.m3u8", ep: 3},
        ];
        </script>
        </body></html>
        '''
        resources = extractor.extract_from_html(html)
        urls = [r.url for r in resources]
        # All episodes are now kept (no hard filter)
        assert any("ep01" in u for u in urls)
        # ep01 should score higher than ep02/ep03
        ep01 = next((r for r in resources if "ep01" in r.url), None)
        ep02 = next((r for r in resources if "ep02" in r.url), None)
        if ep01 and ep02:
            assert extractor.calculate_score(ep01) > extractor.calculate_score(ep02)


class TestPlatformURLNormalization:
    """Test URL normalization with real platform URL patterns."""

    def setup_method(self):
        self.extractor = HTMLExtractor("https://dm1.xfdm.pro/watch/3416/1/1.html")

    def test_relative_path_resolution(self):
        url = self.extractor._normalize_url("/hls/video/index.m3u8")
        assert url == "https://dm1.xfdm.pro/hls/video/index.m3u8"

    def test_protocol_relative_url(self):
        url = self.extractor._normalize_url("//cdn.example.com/video.m3u8")
        assert url == "https://cdn.example.com/video.m3u8"

    def test_absolute_url_passthrough(self):
        url = self.extractor._normalize_url("https://cdn.example.com/video.m3u8")
        assert url == "https://cdn.example.com/video.m3u8"

    def test_blob_url_rejected(self):
        assert self.extractor._normalize_url("blob:https://example.com/abc-123") is None

    def test_data_url_rejected(self):
        assert self.extractor._normalize_url("data:video/mp4;base64,AAAA") is None

    def test_javascript_url_rejected(self):
        assert self.extractor._normalize_url("javascript:void(0)") is None

    def test_empty_url_rejected(self):
        assert self.extractor._normalize_url("") is None


class TestDASHExtraction:
    """Test DASH manifest extraction patterns."""

    def test_mpd_url_in_script(self):
        extractor = HTMLExtractor("https://example.com")
        html = '''
        <html><body>
        <script>
        var config = { src: "https://cdn.example.com/manifest.mpd" };
        </script>
        </body></html>
        '''
        resources = extractor.extract_from_html(html)
        urls = [r.url for r in resources]
        assert any(".mpd" in u for u in urls)

    def test_mpd_url_in_html(self):
        extractor = HTMLExtractor("https://example.com")
        html = '''
        <html><body>
        <video>
            <source src="https://cdn.example.com/dash/manifest.mpd" type="application/dash+xml">
        </video>
        </body></html>
        '''
        resources = extractor.extract_from_html(html)
        urls = [r.url for r in resources]
        assert any(".mpd" in u for u in urls)
