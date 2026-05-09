"""HTML static scanning for video resources."""

import json
import re
from typing import Optional
from urllib.parse import urljoin, urlparse, unquote

from ..constants import (
    VIDEO_EXTENSIONS,
    HLS_EXTENSIONS,
    DASH_EXTENSIONS,
    TEMPORARY_URL_INDICATORS,
    PLAYER_CONFIG_KEYS,
    SCORE_WEIGHTS,
)
from ..schemas import MediaType, DiscoveryMethod

# Player API endpoints and other non-media paths to ignore
_PLAYER_API_BLACKLIST = {
    "/player/src", "/player/volume", "/player/currenttime", "/player/duration",
    "/player/videowidth", "/player/videoheight", "/player/paused", "/player/ended",
    "/player/muted", "/player/loop", "/player/playbackrate", "/player/ready",
    "/player/error", "/player/buffered", "/player/seekable", "/player/networkstate",
    "/player/readystate", "/player/autoplay", "/player/controls", "/player/loop",
}

# Common API endpoint patterns that are not media resources
_API_PATH_PATTERNS = re.compile(
    r'/api/|/ajax/|/json/|/rest/|/graphql|/callback|/jsonp|/ping|/health|/status',
    re.IGNORECASE,
)


class ExtractedResource:
    """Extracted video resource."""

    def __init__(
        self,
        url: str,
        media_type: MediaType,
        discovery_method: DiscoveryMethod,
        source_frame_url: Optional[str] = None,
        content_type: Optional[str] = None,
        title: Optional[str] = None,
        resolution: Optional[str] = None,
        raw_info: Optional[dict] = None,
    ):
        self.url = url
        self.media_type = media_type
        self.discovery_method = discovery_method
        self.source_frame_url = source_frame_url
        self.content_type = content_type
        self.title = title
        self.resolution = resolution
        self.raw_info = raw_info or {}


class HTMLExtractor:
    """Extract video resources from HTML content."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self._player_config_keys = {key.lower() for key in PLAYER_CONFIG_KEYS}
        self._url_pattern = re.compile(
            r'https?://[^\s\'"<>]+(?:'
            + '|'.join(re.escape(ext) for ext in VIDEO_EXTENSIONS | HLS_EXTENSIONS | DASH_EXTENSIONS)
            + r')[^\s\'"<>]*',
            re.IGNORECASE
        )
        self._m3u8_pattern = re.compile(r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*', re.IGNORECASE)
        self._mpd_pattern = re.compile(r'https?://[^\s\'"<>]+\.mpd[^\s\'"<>]*', re.IGNORECASE)
        self._video_pattern = re.compile(r'https?://[^\s\'"<>]+\.(?:mp4|webm|mkv|avi|mov|flv)[^\s\'"<>]*', re.IGNORECASE)

    def extract_from_html(self, html: str, frame_url: Optional[str] = None) -> list[ExtractedResource]:
        """Extract video resources from HTML content."""
        resources = []
        seen_urls = set()  # Stores canonical (decoded, lowercased) URLs

        # Extract from video/source tags
        resources.extend(self._extract_from_video_tags(html, frame_url, seen_urls))

        # Extract from script tags (player configs)
        resources.extend(self._extract_from_scripts(html, frame_url, seen_urls))

        # Extract from data attributes
        resources.extend(self._extract_from_data_attributes(html, frame_url, seen_urls))

        # Extract URLs directly from HTML
        resources.extend(self._extract_urls_from_html(html, frame_url, seen_urls))

        return resources

    def _extract_from_video_tags(
        self, html: str, frame_url: Optional[str], seen_urls: set
    ) -> list[ExtractedResource]:
        """Extract from <video> and <source> tags."""
        resources = []

        # Match <video src="..."> or <source src="...">
        video_src_pattern = re.compile(
            r'<(?:video|source)[^>]+src=["\']([^"\']+)["\']',
            re.IGNORECASE
        )
        for match in video_src_pattern.finditer(html):
            url = self._normalize_url(match.group(1), frame_url)
            if url:
                canonical = self._canonical_url(url)
                if canonical not in seen_urls:
                    seen_urls.add(canonical)
                    media_type = self._detect_media_type(url)
                    resources.append(ExtractedResource(
                        url=url,
                        media_type=media_type,
                        discovery_method=DiscoveryMethod.HTML,
                        source_frame_url=frame_url,
                    ))

        return resources

    def _extract_from_scripts(
        self, html: str, frame_url: Optional[str], seen_urls: set
    ) -> list[ExtractedResource]:
        """Extract from script tags containing player configurations."""
        resources = []

        # Find script tags
        script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
        for script_match in script_pattern.finditer(html):
            script_content = script_match.group(1)

            # Try to find JSON configurations
            json_pattern = re.compile(r'(?:var\s+\w+\s*=\s*|JSON\.parse\s*\(\s*["\'])(.*?)(?:;?\s*$|["\'])', re.MULTILINE)
            for json_match in json_pattern.finditer(script_content):
                try:
                    json_str = json_match.group(1)
                    config = json.loads(json_str)
                    resources.extend(
                        self._extract_from_json_config(config, frame_url, seen_urls)
                    )
                except (json.JSONDecodeError, ValueError):
                    pass

            # Try to find direct URL assignments
            url_assign_pattern = re.compile(
                r'(?P<key>src|file|url|source|video_url|videoUrl|stream_url|streamUrl)\s*[:=]\s*["\'](?P<url>[^"\']+)["\']',
                re.IGNORECASE
            )
            for url_match in url_assign_pattern.finditer(script_content):
                key_hint = url_match.group("key")
                url = self._normalize_url(url_match.group("url"), frame_url)
                if url and self._looks_like_media_resource(url, key_hint=key_hint):
                    canonical = self._canonical_url(url)
                    if canonical not in seen_urls:
                        seen_urls.add(canonical)
                        media_type = self._detect_media_type(url)
                        resources.append(ExtractedResource(
                            url=url,
                            media_type=media_type,
                            discovery_method=DiscoveryMethod.PLAYER_CONFIG,
                            source_frame_url=frame_url,
                        ))

        return resources

    def _extract_from_json_config(
        self, config: dict, frame_url: Optional[str], seen_urls: set
    ) -> list[ExtractedResource]:
        """Extract URLs from JSON configuration."""
        resources = []

        if isinstance(config, dict):
            for key, value in config.items():
                if (
                    isinstance(value, str)
                    and self._is_url(value)
                    and self._looks_like_media_resource(value, key_hint=key)
                ):
                    url = self._normalize_url(value, frame_url)
                    if url:
                        canonical = self._canonical_url(url)
                        if canonical not in seen_urls:
                            seen_urls.add(canonical)
                            media_type = self._detect_media_type(url)
                            resources.append(ExtractedResource(
                                url=url,
                                media_type=media_type,
                                discovery_method=DiscoveryMethod.PLAYER_CONFIG,
                                source_frame_url=frame_url,
                            ))
                elif isinstance(value, (dict, list)):
                    resources.extend(
                        self._extract_from_json_config(value, frame_url, seen_urls)
                    )
        elif isinstance(config, list):
            for item in config:
                if isinstance(item, (dict, list)):
                    resources.extend(
                        self._extract_from_json_config(item, frame_url, seen_urls)
                    )

        return resources

    def _extract_from_data_attributes(
        self, html: str, frame_url: Optional[str], seen_urls: set
    ) -> list[ExtractedResource]:
        """Extract from data attributes."""
        resources = []

        # Match data-video-url, data-src, etc.
        data_attr_pattern = re.compile(
            r'data-(?:video-url|src|url|href|video|stream|media|file)=["\']([^"\']+)["\']',
            re.IGNORECASE
        )
        for match in data_attr_pattern.finditer(html):
            url = self._normalize_url(match.group(1), frame_url)
            if url and self._looks_like_media_resource(url):
                canonical = self._canonical_url(url)
                if canonical not in seen_urls:
                    seen_urls.add(canonical)
                    media_type = self._detect_media_type(url)
                    resources.append(ExtractedResource(
                        url=url,
                        media_type=media_type,
                        discovery_method=DiscoveryMethod.HTML,
                        source_frame_url=frame_url,
                    ))

        return resources

    def _extract_urls_from_html(
        self, html: str, frame_url: Optional[str], seen_urls: set
    ) -> list[ExtractedResource]:
        """Extract video URLs directly from HTML content."""
        resources = []

        # Extract m3u8 URLs
        for match in self._m3u8_pattern.finditer(html):
            url = self._normalize_url(match.group(0), frame_url)
            if url and self._looks_like_media_resource(url):
                canonical = self._canonical_url(url)
                if canonical not in seen_urls:
                    seen_urls.add(canonical)
                    resources.append(ExtractedResource(
                        url=url,
                        media_type=MediaType.HLS,
                        discovery_method=DiscoveryMethod.HTML,
                        source_frame_url=frame_url,
                    ))

        # Extract mpd URLs
        for match in self._mpd_pattern.finditer(html):
            url = self._normalize_url(match.group(0), frame_url)
            if url and self._looks_like_media_resource(url):
                canonical = self._canonical_url(url)
                if canonical not in seen_urls:
                    seen_urls.add(canonical)
                    resources.append(ExtractedResource(
                        url=url,
                        media_type=MediaType.DASH,
                        discovery_method=DiscoveryMethod.HTML,
                        source_frame_url=frame_url,
                    ))

        # Extract direct video URLs
        for match in self._video_pattern.finditer(html):
            url = self._normalize_url(match.group(0), frame_url)
            if url and self._looks_like_media_resource(url):
                canonical = self._canonical_url(url)
                if canonical not in seen_urls:
                    seen_urls.add(canonical)
                    resources.append(ExtractedResource(
                        url=url,
                        media_type=self._detect_media_type(url),
                        discovery_method=DiscoveryMethod.HTML,
                        source_frame_url=frame_url,
                    ))

        return resources

    def _normalize_url(self, url: str, frame_url: Optional[str] = None) -> Optional[str]:
        """Normalize and resolve URL."""
        if not url:
            return None

        # Remove quotes and whitespace
        url = url.strip().strip("'\"")

        # Skip non-HTTP URLs
        if not url.startswith(('http://', 'https://', '//')):
            # Try to resolve relative URL
            base = frame_url or self.base_url
            if base:
                url = urljoin(base, url)
            else:
                return None

        # Add protocol if missing
        if url.startswith('//'):
            url = 'https:' + url

        return url

    @staticmethod
    def _canonical_url(url: str) -> str:
        """Return a canonical form of URL for deduplication (decode percent-encoding)."""
        return unquote(url).lower()

    def _is_url(self, text: str) -> bool:
        """Check if text looks like a URL."""
        return bool(re.match(r'https?://', text))

    def _looks_like_media_resource(self, url: str, key_hint: Optional[str] = None) -> bool:
        """Filter obvious non-media URLs from generic HTML/config extraction."""
        parsed = urlparse(url.lower())
        path = parsed.path

        # Blacklist: player API endpoints and similar non-media paths
        if path in _PLAYER_API_BLACKLIST:
            return False

        # Blacklist: common API/AJAX endpoints
        if _API_PATH_PATTERNS.search(path):
            return False

        # Whitelist: known media extensions (exclude .ts which are usually HLS segments)
        standalone_video_exts = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".m4v", ".wmv", ".f4v", ".vob", ".ogv", ".3gp"}
        if any(path.endswith(ext) for ext in HLS_EXTENSIONS | DASH_EXTENSIONS):
            return True
        if any(path.endswith(ext) for ext in standalone_video_exts):
            return True

        # Blacklist: common non-media file extensions
        ignored_exts = (
            ".html", ".htm", ".php", ".jpg", ".jpeg", ".png", ".gif", ".svg",
            ".webp", ".ico", ".css", ".js", ".json", ".xml", ".txt", ".woff",
            ".woff2", ".ttf",
        )
        if any(path.endswith(ext) for ext in ignored_exts):
            return False

        # Whitelist: media-related path keywords
        path_keywords = ("video", "stream", "media", "hls", "dash", "m3u8", "mpd", "download")
        if any(keyword in path for keyword in path_keywords):
            return True

        if key_hint and key_hint.lower() in self._player_config_keys:
            return True

        return False

    def _detect_media_type(self, url: str) -> MediaType:
        """Detect media type from URL."""
        url_lower = url.lower()
        parsed = urlparse(url_lower)
        path = parsed.path

        if any(path.endswith(ext) for ext in HLS_EXTENSIONS):
            return MediaType.HLS
        if any(path.endswith(ext) for ext in DASH_EXTENSIONS):
            return MediaType.DASH
        if any(path.endswith(ext) for ext in VIDEO_EXTENSIONS):
            return MediaType.DIRECT_VIDEO

        return MediaType.UNKNOWN

    def detect_temporary_url(self, url: str) -> bool:
        """Detect if URL appears to be temporary."""
        url_lower = url.lower()
        return any(indicator in url_lower for indicator in TEMPORARY_URL_INDICATORS)

    def calculate_score(self, resource: ExtractedResource) -> int:
        """Calculate score for resource ranking."""
        base_score = 0

        if resource.media_type == MediaType.HLS:
            # Check if it's a master playlist (contains variant streams)
            if "master" in resource.url.lower() or "variant" in resource.url.lower():
                base_score = SCORE_WEIGHTS["master_m3u8"]
            else:
                base_score = SCORE_WEIGHTS["regular_m3u8"]
        elif resource.media_type == MediaType.DASH:
            base_score = SCORE_WEIGHTS["mpd"]
        elif resource.media_type == MediaType.DIRECT_VIDEO:
            base_score = SCORE_WEIGHTS["direct_video"]
        elif resource.media_type == MediaType.PAGE_EXTRACT:
            base_score = SCORE_WEIGHTS["yt_dlp_with_formats"]
        else:
            base_score = SCORE_WEIGHTS["other"]

        # Bonus for network discovery (more reliable)
        if resource.discovery_method == DiscoveryMethod.NETWORK:
            base_score += 5

        # Penalty for temporary URLs
        if self.detect_temporary_url(resource.url):
            base_score -= 10

        return max(0, base_score)
