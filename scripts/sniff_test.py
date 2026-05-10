"""Standalone integration test: sniff real URLs and report results.

Usage:
    python scripts/sniff_test.py                     # test all default URLs
    python scripts/sniff_test.py <url1> <url2> ...   # test specific URLs
    python scripts/sniff_test.py --wait 20           # override wait time
    python scripts/sniff_test.py --headed             # show browser window
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.sniffer import Sniffer
from app.services.extractor import HTMLExtractor


DEFAULT_URLS = [
    "https://www.bilibili.com/video/BV1x6RvB5Egf/",
    "https://d2883ce011d2398b.tbdm01.cc/play/43-4-1.html",
    "https://www.mxdmv.com/mxdmv1/126016_1_1.html",
    "https://dm1.xfdm.pro/watch/3416/1/1.html",
    "https://www.acfun.cn/bangumi/aa5024869",
    "https://www.acfuns.net/vodplay/22646-1-1.html",
    "https://www.netflixgc.com/play/19621-2-1.html",
    "https://m.meijtt.com/v/122421-1-1/",
]

# Patterns that indicate a URL is NOT a real downloadable video resource
NOISE_PATTERNS = [
    "/api/", "/ajax/", "/json/", "/graphql",
    "/analytics", "/tracking", "/beacon",
    "/advertisement", "/ad/", "/ads/",
    ".js?", ".css?", ".json?",
    "google-analytics", "doubleclick",
    "facebook.net", "twitter.com",
]


def is_likely_noise(url: str) -> bool:
    """Heuristic: does this URL look like a non-video resource?"""
    url_lower = url.lower()
    return any(p in url_lower for p in NOISE_PATTERNS)


async def test_sniff(url: str, wait: int = 15, headless: bool = True) -> dict:
    """Sniff a single URL and return results."""
    sniffer = Sniffer(headless=headless, wait_seconds=wait, auto_click=True)
    start = time.time()
    try:
        candidates = await sniffer.sniff(url)
        elapsed = time.time() - start
        return {
            "url": url,
            "success": True,
            "elapsed": round(elapsed, 1),
            "candidates": [
                {
                    "url": c.url,
                    "media_type": c.media_type.value,
                    "discovery_method": c.discovery_method.value,
                    "score": sniffer._html_resources and 0,
                    "title": c.title,
                }
                for c in candidates
            ],
            "total": len(candidates),
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "url": url,
            "success": False,
            "elapsed": round(elapsed, 1),
            "error": str(e),
            "candidates": [],
            "total": 0,
        }


def print_result(result: dict) -> None:
    """Pretty-print a single test result."""
    url = result["url"]
    print(f"\n{'='*80}")
    print(f"URL: {url}")
    print(f"Status: {'OK' if result['success'] else 'FAILED'} | Time: {result['elapsed']}s")

    if not result["success"]:
        print(f"Error: {result.get('error', 'unknown')}")
        return

    candidates = result["candidates"]
    if not candidates:
        print("No candidates found.")
        return

    print(f"Found {result['total']} candidate(s):")
    print(f"{'─'*80}")

    real_count = 0
    noise_count = 0

    for i, c in enumerate(candidates, 1):
        noise = is_likely_noise(c["url"])
        tag = "NOISE" if noise else "VIDEO"
        if noise:
            noise_count += 1
        else:
            real_count += 1

        url_display = c["url"][:100] + "..." if len(c["url"]) > 100 else c["url"]
        print(f"  [{tag}] {c['media_type']:12s} | {c['discovery_method']:14s} | {url_display}")
        if c.get("title"):
            print(f"         title: {c['title']}")

    print(f"\n  Summary: {real_count} real, {noise_count} noise")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sniff real URLs for video resources")
    parser.add_argument("urls", nargs="*", help="URLs to test (default: built-in list)")
    parser.add_argument("--wait", type=int, default=15, help="Wait seconds per page")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    args = parser.parse_args()

    urls = args.urls if args.urls else DEFAULT_URLS
    print(f"Testing {len(urls)} URLs (wait={args.wait}s, headless={not args.headed})")

    results = []
    for url in urls:
        result = await test_sniff(url, wait=args.wait, headless=not args.headed)
        print_result(result)
        results.append(result)

    # Final summary
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    ok = sum(1 for r in results if r["success"] and r["total"] > 0)
    fail = sum(1 for r in results if not r["success"])
    empty = sum(1 for r in results if r["success"] and r["total"] == 0)
    print(f"  {ok} found video, {empty} no candidates, {fail} errors")
    print(f"  Total: {len(urls)} URLs tested")


if __name__ == "__main__":
    asyncio.run(main())
