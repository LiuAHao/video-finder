"""Integration tests: sniff real URLs and verify video resource discovery.

These tests hit real websites and are slow. Run with:
    pytest tests/test_integration.py --run-slow -v
    pytest tests/test_integration.py -m slow -v
"""

import pytest
from app.services.sniffer import Sniffer
from app.schemas import MediaType


# ── Noise patterns: URLs that should NOT appear as candidates ────────────────

NOISE_PATTERNS = [
    "/api/", "/ajax/", "/json/", "/graphql",
    "/analytics", "/tracking", "/beacon",
    "google-analytics", "doubleclick",
    "facebook.net", "twitter.com",
    ".js?", ".css?",
]


def is_noise(url: str) -> bool:
    url_lower = url.lower()
    return any(p in url_lower for p in NOISE_PATTERNS)


def has_real_candidate(candidates: list) -> bool:
    """Check if at least one candidate looks like a real video resource."""
    for c in candidates:
        if c.media_type in (MediaType.HLS, MediaType.DASH, MediaType.DIRECT_VIDEO):
            if not is_noise(c.url):
                return True
    return False


def noise_ratio(candidates: list) -> float:
    """Return fraction of candidates that look like noise."""
    if not candidates:
        return 0.0
    noise = sum(1 for c in candidates if is_noise(c.url))
    return noise / len(candidates)


# ── Test cases ───────────────────────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.asyncio
async def test_sniff_bilibili():
    """Bilibili: yt-dlp should find formats."""
    sniffer = Sniffer(headless=True, wait_seconds=15, auto_click=True)
    candidates = await sniffer.sniff("https://www.bilibili.com/video/BV1x6RvB5Egf/")
    assert len(candidates) > 0, "Should find at least one candidate"
    assert has_real_candidate(candidates) or any(
        c.media_type == MediaType.PAGE_EXTRACT for c in candidates
    ), "Should find video or page-level yt-dlp candidate"
    assert noise_ratio(candidates) < 0.5, "More than half are noise"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sniff_tbdm():
    """tbdm01.cc anime site."""
    sniffer = Sniffer(headless=True, wait_seconds=20, auto_click=True)
    candidates = await sniffer.sniff("https://d2883ce011d2398b.tbdm01.cc/play/43-4-1.html")
    assert len(candidates) > 0, "Should find at least one candidate"
    assert has_real_candidate(candidates), "Should find HLS/DASH/direct video"
    assert noise_ratio(candidates) < 0.5


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sniff_mxdmv():
    """mxdmv.com anime site."""
    sniffer = Sniffer(headless=True, wait_seconds=20, auto_click=True)
    candidates = await sniffer.sniff("https://www.mxdmv.com/mxdmv1/126016_1_1.html")
    assert len(candidates) > 0, "Should find at least one candidate"
    assert has_real_candidate(candidates), "Should find video resource"
    assert noise_ratio(candidates) < 0.5


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sniff_xfdm():
    """xfdm.pro anime site."""
    sniffer = Sniffer(headless=True, wait_seconds=20, auto_click=True)
    candidates = await sniffer.sniff("https://dm1.xfdm.pro/watch/3416/1/1.html")
    assert len(candidates) > 0, "Should find at least one candidate"
    assert has_real_candidate(candidates), "Should find video resource"
    assert noise_ratio(candidates) < 0.5


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sniff_acfun():
    """AcFun: should find video or yt-dlp fallback."""
    sniffer = Sniffer(headless=True, wait_seconds=15, auto_click=True)
    candidates = await sniffer.sniff("https://www.acfun.cn/bangumi/aa5024869")
    assert len(candidates) > 0, "Should find at least one candidate"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sniff_acfuns():
    """acfuns.net anime site."""
    sniffer = Sniffer(headless=True, wait_seconds=20, auto_click=True)
    candidates = await sniffer.sniff("https://www.acfuns.net/vodplay/22646-1-1.html")
    assert len(candidates) > 0, "Should find at least one candidate"
    assert has_real_candidate(candidates), "Should find video resource"
    assert noise_ratio(candidates) < 0.5


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sniff_netflixgc():
    """netflixgc.com anime site."""
    sniffer = Sniffer(headless=True, wait_seconds=20, auto_click=True)
    candidates = await sniffer.sniff("https://www.netflixgc.com/play/19621-2-1.html")
    assert len(candidates) > 0, "Should find at least one candidate"
    assert has_real_candidate(candidates), "Should find video resource"
    assert noise_ratio(candidates) < 0.5


@pytest.mark.slow
@pytest.mark.asyncio
async def test_sniff_meijtt():
    """meijtt.com anime site."""
    sniffer = Sniffer(headless=True, wait_seconds=20, auto_click=True)
    candidates = await sniffer.sniff("https://m.meijtt.com/v/122421-1-1/")
    assert len(candidates) > 0, "Should find at least one candidate"
    assert has_real_candidate(candidates), "Should find video resource"
    assert noise_ratio(candidates) < 0.5


# ── Result reporting (runs after all tests) ──────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
def report_summary():
    """Print a summary after all integration tests."""
    yield
    print("\n" + "=" * 60)
    print("Integration test session complete.")
    print("=" * 60)
