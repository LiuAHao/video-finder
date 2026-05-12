"""Main entry point for the application."""

import sys
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from . import configure_runtime_environment

configure_runtime_environment()

from .config import get_settings
from .db.database import init_db, close_db
from .web.routes import router


def create_app() -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()
    settings.ensure_directories()

    app = FastAPI(
        title="Video Finder",
        description="Video discovery and download tool",
        version="0.1.0",
    )

    # Mount static files
    static_dir = Path(__file__).parent / "web" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include routes
    app.include_router(router)

    # Startup event
    @app.on_event("startup")
    async def startup():
        await init_db()

    # Shutdown event
    @app.on_event("shutdown")
    async def shutdown():
        await close_db()

    return app


app = create_app()


def run_server(host: str = "127.0.0.1", port: int = 7860):
    """Run the server."""
    reload_enabled = sys.platform != "win32"

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
    )


if __name__ == "__main__":
    settings = get_settings()
    run_server(host=settings.host, port=settings.port)
