"""Video Finder - Local video discovery and download tool."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

__version__ = "0.1.0"


def ensure_compatible_event_loop_policy() -> None:
    """Ensure Windows uses an event loop policy that supports subprocesses."""
    if sys.platform != "win32":
        return

    try:
        current_policy = asyncio.get_event_loop_policy()
        if isinstance(current_policy, asyncio.WindowsProactorEventLoopPolicy):
            return
    except Exception:
        pass

    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def configure_runtime_environment() -> None:
    """Configure runtime defaults needed by the local environment."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    ensure_compatible_event_loop_policy()

    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return

    local_browsers = (
        Path(__file__).resolve().parent.parent
        / "venv"
        / "Lib"
        / "site-packages"
        / "playwright"
        / "driver"
        / "package"
        / ".local-browsers"
    )
    if local_browsers.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
