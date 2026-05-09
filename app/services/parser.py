"""Resource parsing for HLS, DASH, and yt-dlp output."""

import json
import re
from typing import Optional
from urllib.parse import urljoin

import httpx

from ..schemas import MediaType


class HLSVariant:
    """HLS variant stream."""

    def __init__(
        self,
        url: str,
        bandwidth: int,
        resolution: Optional[str] = None,
        codecs: Optional[str] = None,
        audio: Optional[str] = None,
    ):
        self.url = url
        self.bandwidth = bandwidth
        self.resolution = resolution
        self.codecs = codecs
        self.audio = audio


class DASHRepresentation:
    """DASH representation."""

    def __init__(
        self,
        url: str,
        bandwidth: int,
        resolution: Optional[str] = None,
        codecs: Optional[str] = None,
        mime_type: Optional[str] = None,
    ):
        self.url = url
        self.bandwidth = bandwidth
        self.resolution = resolution
        self.codecs = codecs
        self.mime_type = mime_type


class YtdlpFormat:
    """yt-dlp format."""

    def __init__(
        self,
        format_id: str,
        ext: str,
        resolution: Optional[str] = None,
        fps: Optional[int] = None,
        vcodec: Optional[str] = None,
        acodec: Optional[str] = None,
        filesize: Optional[int] = None,
        tbr: Optional[float] = None,
        url: Optional[str] = None,
    ):
        self.format_id = format_id
        self.ext = ext
        self.resolution = resolution
        self.fps = fps
        self.vcodec = vcodec
        self.acodec = acodec
        self.filesize = filesize
        self.tbr = tbr
        self.url = url


class HLSParser:
    """Parse HLS playlists."""

    async def parse_master_playlist(self, url: str, referer: Optional[str] = None) -> list[HLSVariant]:
        """Parse HLS master playlist and return variants."""
        try:
            content = await self._fetch_content(url, referer)
            return self._parse_master_playlist_content(content, url)
        except Exception as e:
            raise ValueError(f"Failed to parse HLS playlist: {e}")

    async def parse_media_playlist(self, url: str, referer: Optional[str] = None) -> dict:
        """Parse HLS media playlist."""
        try:
            content = await self._fetch_content(url, referer)
            return self._parse_media_playlist_content(content, url)
        except Exception as e:
            raise ValueError(f"Failed to parse HLS media playlist: {e}")

    async def _fetch_content(self, url: str, referer: Optional[str] = None) -> str:
        """Fetch playlist content."""
        headers = {}
        if referer:
            headers["Referer"] = referer

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text

    def _parse_master_playlist_content(self, content: str, base_url: str) -> list[HLSVariant]:
        """Parse master playlist content."""
        variants = []
        lines = content.strip().split("\n")

        current_bandwidth = 0
        current_resolution = None
        current_codecs = None
        current_audio = None

        for line in lines:
            line = line.strip()

            if line.startswith("#EXT-X-STREAM-INF:"):
                # Parse stream info
                attrs = self._parse_attributes(line[18:])
                current_bandwidth = int(attrs.get("BANDWIDTH", 0))
                current_resolution = attrs.get("RESOLUTION")
                current_codecs = attrs.get("CODECS")
                current_audio = attrs.get("AUDIO")

            elif line and not line.startswith("#"):
                # This is a URI line
                variant_url = urljoin(base_url, line)
                variants.append(HLSVariant(
                    url=variant_url,
                    bandwidth=current_bandwidth,
                    resolution=current_resolution,
                    codecs=current_codecs,
                    audio=current_audio,
                ))
                # Reset for next variant
                current_bandwidth = 0
                current_resolution = None
                current_codecs = None
                current_audio = None

        return variants

    def _parse_media_playlist_content(self, content: str, base_url: str) -> dict:
        """Parse media playlist content."""
        info = {
            "segments": 0,
            "duration": 0.0,
            "target_duration": 0,
            "is_live": False,
            "encryption": None,
        }

        lines = content.strip().split("\n")
        segment_count = 0
        total_duration = 0.0

        for line in lines:
            line = line.strip()

            if line.startswith("#EXT-X-TARGETDURATION:"):
                info["target_duration"] = int(line.split(":")[1])

            elif line.startswith("#EXT-X-PLAYLIST-TYPE:"):
                # VOD or EVENT
                pass

            elif line.startswith("#EXT-X-ENDLIST"):
                info["is_live"] = False

            elif line.startswith("#EXTINF:"):
                # Duration
                duration_str = line.split(":")[1].split(",")[0]
                total_duration += float(duration_str)
                segment_count += 1

            elif line.startswith("#EXT-X-KEY:"):
                # Encryption info
                attrs = self._parse_attributes(line[11:])
                if attrs.get("METHOD") != "NONE":
                    info["encryption"] = {
                        "method": attrs.get("METHOD"),
                        "uri": attrs.get("URI"),
                        "iv": attrs.get("IV"),
                    }

        info["segments"] = segment_count
        info["duration"] = total_duration

        return info

    def _parse_attributes(self, line: str) -> dict:
        """Parse EXT-X attributes."""
        attrs = {}
        parts = []
        current = []
        in_quotes = False

        for char in line:
            if char == '"':
                in_quotes = not in_quotes
                current.append(char)
            elif char == "," and not in_quotes:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)

        if current:
            parts.append("".join(current).strip())

        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            attrs[key.strip()] = value.strip().strip('"')
        return attrs


class DASHParser:
    """Parse DASH manifests."""

    async def parse_manifest(self, url: str, referer: Optional[str] = None) -> list[DASHRepresentation]:
        """Parse DASH manifest and return representations."""
        try:
            content = await self._fetch_content(url, referer)
            return self._parse_manifest_content(content, url)
        except Exception as e:
            raise ValueError(f"Failed to parse DASH manifest: {e}")

    async def _fetch_content(self, url: str, referer: Optional[str] = None) -> str:
        """Fetch manifest content."""
        headers = {}
        if referer:
            headers["Referer"] = referer

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            return response.text

    def _parse_manifest_content(self, content: str, base_url: str) -> list[DASHRepresentation]:
        """Parse DASH manifest content."""
        representations = []

        # Simple regex-based parsing (for MVP)
        # In production, use xml.etree.ElementTree

        # Find AdaptationSet blocks
        adaptation_pattern = re.compile(
            r'<AdaptationSet[^>]*>(.*?)</AdaptationSet>',
            re.DOTALL
        )

        for adaptation_match in adaptation_pattern.finditer(content):
            adaptation_content = adaptation_match.group(1)

            # Find Representation blocks
            representation_pattern = re.compile(
                r'<Representation[^>]*>',
                re.DOTALL
            )

            for rep_match in representation_pattern.finditer(adaptation_content):
                rep_tag = rep_match.group(0)

                # Parse attributes
                attrs = self._parse_xml_attributes(rep_tag)

                # Get base URL if present
                base_url_match = re.search(
                    r'<BaseURL>(.*?)</BaseURL>',
                    adaptation_content
                )
                rep_url = base_url_match.group(1) if base_url_match else None

                if rep_url:
                    rep_url = urljoin(base_url, rep_url)

                representations.append(DASHRepresentation(
                    url=rep_url or base_url,
                    bandwidth=int(attrs.get("bandwidth", 0)),
                    resolution=f"{attrs.get('width', '?')}x{attrs.get('height', '?')}",
                    codecs=attrs.get("codecs"),
                    mime_type=attrs.get("mimeType"),
                ))

        return representations

    def _parse_xml_attributes(self, tag: str) -> dict:
        """Parse XML tag attributes."""
        attrs = {}
        pattern = re.compile(r'(\w+)="([^"]+)"')
        for match in pattern.finditer(tag):
            attrs[match.group(1)] = match.group(2)
        return attrs


class YtdlpParser:
    """Parse yt-dlp output."""

    def parse_formats(self, json_output: dict) -> list[YtdlpFormat]:
        """Parse yt-dlp --dump-json output."""
        formats = []

        for fmt in json_output.get("formats", []):
            formats.append(YtdlpFormat(
                format_id=fmt.get("format_id", ""),
                ext=fmt.get("ext", ""),
                resolution=fmt.get("resolution"),
                fps=fmt.get("fps"),
                vcodec=fmt.get("vcodec"),
                acodec=fmt.get("acodec"),
                filesize=fmt.get("filesize"),
                tbr=fmt.get("tbr"),
                url=fmt.get("url"),
            ))

        return formats

    def get_best_format(self, formats: list[YtdlpFormat]) -> Optional[YtdlpFormat]:
        """Get best format based on resolution and bitrate."""
        if not formats:
            return None

        # Filter video formats
        video_formats = [f for f in formats if f.vcodec and f.vcodec != "none"]

        if not video_formats:
            return formats[0]

        # Sort by resolution and bitrate
        def sort_key(fmt: YtdlpFormat) -> tuple:
            resolution = 0
            if fmt.resolution:
                match = re.search(r'(\d+)x(\d+)', fmt.resolution)
                if match:
                    resolution = int(match.group(2))
            return (resolution, fmt.tbr or 0)

        video_formats.sort(key=sort_key, reverse=True)
        return video_formats[0]
