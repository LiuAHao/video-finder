"""Playwright-based network sniffer for video resources."""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse, unquote

from playwright.async_api import async_playwright, Page, Browser, Response, Request

from ..config import get_settings
from ..constants import (
    VIDEO_EXTENSIONS,
    HLS_EXTENSIONS,
    DASH_EXTENSIONS,
    VIDEO_CONTENT_TYPES,
    HLS_CONTENT_TYPES,
    DASH_CONTENT_TYPES,
    DRM_INDICATORS,
    PLAY_BUTTON_SELECTORS,
)
from ..schemas import MediaType, DiscoveryMethod
from .extractor import HTMLExtractor, ExtractedResource
from ..downloaders.ytdlp import YtdlpProbe


class NetworkResource:
    """Resource discovered from network request."""

    def __init__(
        self,
        url: str,
        method: str,
        resource_type: str,
        content_type: Optional[str] = None,
        status: Optional[int] = None,
        frame_url: Optional[str] = None,
    ):
        self.url = url
        self.method = method
        self.resource_type = resource_type
        self.content_type = content_type
        self.status = status
        self.frame_url = frame_url


class Sniffer:
    """Playwright-based video resource sniffer."""

    def __init__(
        self,
        headless: bool = True,
        wait_seconds: int = 10,
        auto_click: bool = True,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ):
        self.headless = headless
        self.wait_seconds = wait_seconds
        self.auto_click = auto_click
        self.user_agent = user_agent
        self.referer = referer
        self.on_progress = on_progress or (lambda msg: None)

        self._network_resources: list[NetworkResource] = []
        self._html_resources: list[ExtractedResource] = []
        self._all_candidates: list[ExtractedResource] = []
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    def _log(self, message: str) -> None:
        """Log progress message."""
        self.on_progress(message)

    async def sniff(self, url: str) -> list[ExtractedResource]:
        """Sniff a page for video resources."""
        self._log(f"Starting sniff for: {url}")

        try:
            async with async_playwright() as p:
                # Launch browser
                self._log("Launching browser...")
                self._browser = await p.chromium.launch(headless=self.headless)

                # Create context
                context_options = {}
                if self.user_agent:
                    context_options["user_agent"] = self.user_agent
                if self.referer:
                    context_options["extra_http_headers"] = {"Referer": self.referer}

                context = await self._browser.new_context(**context_options)
                self._page = await context.new_page()

                # Setup network monitoring
                self._setup_network_monitoring()

                # Navigate to page
                self._log("Navigating to page...")
                try:
                    await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    self._log(f"Navigation error: {e}")

                # Wait for video resources to appear (poll every 1s, max wait_seconds)
                self._log(f"Waiting for video resources (max {self.wait_seconds}s)...")
                waited = 0
                while waited < self.wait_seconds:
                    await asyncio.sleep(1)
                    waited += 1
                    # Check if we already found video resources from network
                    has_video = any(
                        self._is_potential_video_url(r.url)
                        for r in self._network_resources
                    )
                    if has_video:
                        self._log(f"Found video resources after {waited}s, early stop")
                        break

                # Try to click play button
                if self.auto_click:
                    await self._try_click_play()

                # Wait a bit more after clicking (poll for new resources)
                for _ in range(3):
                    await asyncio.sleep(1)
                    has_new = any(
                        self._is_potential_video_url(r.url)
                        for r in self._network_resources
                    )
                    if has_new and len(self._network_resources) > 0:
                        break

                # Capture page title for use as filename
                page_title = ""
                try:
                    page_title = (await self._page.title()).strip()
                except Exception:
                    pass

                # Extract from HTML
                self._log("Extracting from page HTML...")
                html = await self._page.content()
                extractor = HTMLExtractor(url)
                self._html_resources = extractor.extract_from_html(html)

                # Also extract from iframes
                await self._extract_from_iframes(extractor)

                # Probe the original page with yt-dlp as a general fallback.
                await self._probe_with_ytdlp(url)

                # Combine all candidates
                self._all_candidates = self._combine_candidates(url)

                # Set page title on all candidates
                if page_title:
                    for c in self._all_candidates:
                        if not c.title:
                            c.title = page_title

                # Check for DRM
                self._check_drm(html)

                self._log(f"Found {len(self._all_candidates)} candidates")

                return self._all_candidates

        except Exception as e:
            self._log(f"Sniffer error: {e}")
            raise
        finally:
            await self._cleanup()

    def _setup_network_monitoring(self) -> None:
        """Setup network request/response monitoring."""
        if not self._page:
            return

        # Monitor requests
        self._page.on("request", self._on_request)

        # Monitor responses
        self._page.on("response", self._on_response)

    def _on_request(self, request: Request) -> None:
        """Handle network request."""
        url = request.url
        resource_type = request.resource_type

        # Filter out non-media requests
        if resource_type in ("document", "stylesheet", "script", "image", "font"):
            return

        # Filter out HLS segment .ts files (these are fragments, not standalone videos)
        if self._is_hls_segment(url):
            return

        # Check if URL looks like a video resource
        if self._is_potential_video_url(url):
            self._network_resources.append(NetworkResource(
                url=url,
                method=request.method,
                resource_type=resource_type,
                frame_url=request.frame.url if request.frame else None,
            ))

    def _on_response(self, response: Response) -> None:
        """Handle network response."""
        url = response.url
        content_type = response.headers.get("content-type", "")
        status = response.status

        # Filter out HLS segment .ts files (must match _on_request filter)
        if self._is_hls_segment(url):
            return

        # Check content type
        if any(ct in content_type.lower() for ct in VIDEO_CONTENT_TYPES):
            # Update existing resource or add new one
            for resource in self._network_resources:
                if resource.url == url:
                    resource.content_type = content_type
                    resource.status = status
                    return

            self._network_resources.append(NetworkResource(
                url=url,
                method="GET",
                resource_type="media",
                content_type=content_type,
                status=status,
                frame_url=response.frame.url if response.frame else None,
            ))

    def _is_potential_video_url(self, url: str) -> bool:
        """Check if URL might be a video resource."""
        url_lower = url.lower()
        parsed = urlparse(url_lower)
        path = parsed.path

        # Check file extension (exclude .ts which are usually HLS segments)
        standalone_video_exts = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".m4v", ".wmv", ".f4v", ".vob", ".ogv", ".3gp"}
        if any(path.endswith(ext) for ext in standalone_video_exts):
            return True

        # Check HLS/DASH manifests
        if any(path.endswith(ext) for ext in HLS_EXTENSIONS | DASH_EXTENSIONS):
            return True

        # Check common video URL patterns (excluding /hls/ which is segment path)
        video_patterns = [
            r'\.m3u8',
            r'\.mpd',
            r'\.mp4',
            r'/video/',
            r'/stream/',
            r'/media/',
            r'/dash/',
        ]
        if any(re.search(pattern, url_lower) for pattern in video_patterns):
            return True

        return False

    @staticmethod
    def _is_hls_segment(url: str) -> bool:
        """Check if URL is an HLS transport stream segment (not a standalone video)."""
        url_lower = url.lower()
        parsed = urlparse(url_lower)
        path = parsed.path

        if not path.endswith('.ts'):
            return False

        # HLS segment indicators
        hls_indicators = [
            '/hls/',           # Path contains /hls/
            '/hls',            # Path ends with /hls
            'hash=',           # Auth token typical of CDN segments
            '/seg/',           # Segment directory
            '/segment',        # Segment directory
            '/chunk',          # Chunk directory
        ]
        if any(indicator in url_lower for indicator in hls_indicators):
            return True

        # Numeric .ts filename pattern (e.g., 192a1cdcb0b633d3b02c56a3f306cc9d.ts)
        filename = Path(path).stem
        if re.match(r'^[0-9a-f]{16,}$', filename):
            return True

        # Sequential segment pattern (e.g., 00001.ts, seg-1-v1-a1.ts)
        if re.match(r'^(seg|segment|chunk|part)[-_]?\d+', filename, re.IGNORECASE):
            return True
        if re.match(r'^\d{3,}$', filename):
            return True

        return False

    async def _try_click_play(self) -> None:
        """Try to click play button."""
        if not self._page:
            return

        self._log("Trying to click play button...")

        for selector in PLAY_BUTTON_SELECTORS:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    await element.click(timeout=2000)
                    self._log(f"Clicked: {selector}")
                    return
            except Exception:
                continue

        # Try clicking at page center as last resort
        try:
            await self._page.mouse.click(400, 300)
            self._log("Clicked at page center")
        except Exception:
            pass

    async def _extract_from_iframes(self, extractor: HTMLExtractor) -> None:
        """Extract resources from iframes."""
        if not self._page:
            return

        try:
            iframes = await self._page.query_selector_all("iframe")
            for iframe in iframes:
                try:
                    src = await iframe.get_attribute("src")
                    if src:
                        # Navigate to iframe content
                        frame = await iframe.content_frame()
                        if frame:
                            html = await frame.content()
                            iframe_resources = extractor.extract_from_html(html, src)
                            self._html_resources.extend(iframe_resources)
                except Exception:
                    continue
        except Exception:
            pass

    async def _probe_with_ytdlp(self, url: str) -> None:
        """Add a page-level candidate when yt-dlp can parse the URL."""
        self._log("Checking yt-dlp page support...")
        probe = YtdlpProbe(referer=self.referer, user_agent=self.user_agent)
        info = await probe.probe(url)
        if not info:
            return

        resolution = info.get("resolution") or None
        formats = info.get("formats") or []
        if not resolution and formats:
            best_height = max(
                (fmt.get("height") or 0 for fmt in formats if isinstance(fmt, dict)),
                default=0,
            )
            if best_height:
                resolution = f"{best_height}p"

        self._html_resources.append(ExtractedResource(
            url=url,
            media_type=MediaType.PAGE_EXTRACT,
            discovery_method=DiscoveryMethod.YT_DLP,
            source_frame_url=None,
            content_type=None,
            title=info.get("title"),
            resolution=resolution,
            raw_info=info,
        ))

    def _combine_candidates(self, page_url: str) -> list[ExtractedResource]:
        """Combine and deduplicate candidates."""
        seen_canonical = set()
        candidates = []

        def _canonical(url: str) -> str:
            return unquote(url).lower()

        # Add network resources (higher priority)
        for resource in self._network_resources:
            # Second-layer guard: skip HLS segments that slipped through
            if self._is_hls_segment(resource.url):
                continue
            canonical = _canonical(resource.url)
            if canonical not in seen_canonical:
                seen_canonical.add(canonical)
                media_type = self._detect_media_type_from_content_type(
                    resource.content_type, resource.url
                )
                candidates.append(ExtractedResource(
                    url=resource.url,
                    media_type=media_type,
                    discovery_method=DiscoveryMethod.NETWORK,
                    source_frame_url=resource.frame_url,
                    content_type=resource.content_type,
                ))

        # Add HTML resources
        for resource in self._html_resources:
            canonical = _canonical(resource.url)
            if canonical not in seen_canonical:
                seen_canonical.add(canonical)
                candidates.append(resource)

        return candidates

    def _detect_media_type_from_content_type(
        self, content_type: Optional[str], url: str
    ) -> MediaType:
        """Detect media type from content type or URL."""
        if content_type:
            content_type_lower = content_type.lower()
            if any(ct in content_type_lower for ct in HLS_CONTENT_TYPES):
                return MediaType.HLS
            if any(ct in content_type_lower for ct in DASH_CONTENT_TYPES):
                return MediaType.DASH
            if any(ct in content_type_lower for ct in VIDEO_CONTENT_TYPES):
                return MediaType.DIRECT_VIDEO

        # Fallback to URL-based detection
        url_lower = url.lower()
        parsed = urlparse(url_lower)
        path = parsed.path
        if ".m3u8" in url_lower:
            return MediaType.HLS
        if ".mpd" in url_lower:
            return MediaType.DASH
        # Check actual file extension (not just substring)
        standalone_exts = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".m4v", ".wmv"}
        if any(path.endswith(ext) for ext in standalone_exts):
            return MediaType.DIRECT_VIDEO

        return MediaType.UNKNOWN

    def _check_drm(self, html: str) -> None:
        """Check for DRM indicators in HTML."""
        html_lower = html.lower()
        for indicator in DRM_INDICATORS:
            if indicator.lower() in html_lower:
                self._log(f"DRM detected: {indicator}")
                break

    async def _cleanup(self) -> None:
        """Cleanup browser resources."""
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass

    def get_all_candidates(self) -> list[ExtractedResource]:
        """Get all discovered candidates."""
        return self._all_candidates

    def get_network_resources(self) -> list[NetworkResource]:
        """Get network resources."""
        return self._network_resources

    def get_html_resources(self) -> list[ExtractedResource]:
        """Get HTML resources."""
        return self._html_resources
