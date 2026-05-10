"""Web API routes."""

import asyncio
import json
import re
from typing import Optional
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from ..config import get_settings
from ..schemas import (
    SniffRequest,
    SniffResponse,
    SniffResultResponse,
    DownloadRequest,
    DownloadResponse,
    DownloadProgressResponse,
    HistoryResponse,
    HistoryItem,
    ConfigResponse,
    ConfigUpdate,
    TaskStatus,
    MediaType,
    DownloaderType,
)
from ..services.sniffer import Sniffer
from ..services.downloader import DownloadManager
from ..services.storage import StorageService
from ..services.progress import SSEProgressStreamer
from ..services.extractor import HTMLExtractor
from ..services.safety import build_safe_output_path
from ..db.database import get_session_factory

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Global instances
storage = StorageService()
download_manager = DownloadManager()
progress_streamer = SSEProgressStreamer()


# Web UI Routes

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page."""
    return templates.TemplateResponse(request, "index.html")


# API Routes

@router.post("/api/sniff", response_model=SniffResponse)
async def create_sniff_task(request: SniffRequest, background_tasks: BackgroundTasks):
    """Create a sniff task."""
    settings = get_settings()

    # Create task in storage
    task = await storage.create_sniff_task(
        page_url=request.page_url,
        wait_seconds=request.wait_seconds,
        auto_click=request.auto_click,
        headless=request.headless,
        user_agent=request.user_agent or settings.user_agent,
        referer=request.referer,
    )

    # Run sniff in background
    background_tasks.add_task(
        _run_sniff_task,
        task.id,
        request.page_url,
        request.wait_seconds,
        request.auto_click,
        request.headless,
        request.user_agent or settings.user_agent,
        request.referer,
    )

    return SniffResponse(task_id=task.id, status=TaskStatus.RUNNING)


async def _run_sniff_task(
    task_id: str,
    page_url: str,
    wait_seconds: int,
    auto_click: bool,
    headless: bool,
    user_agent: str,
    referer: Optional[str],
):
    """Run sniff task in background."""
    await storage.update_sniff_task(task_id, status="running")

    sniffer = Sniffer(
        headless=headless,
        wait_seconds=wait_seconds,
        auto_click=auto_click,
        user_agent=user_agent,
        referer=referer,
    )

    try:
        candidates = await sniffer.sniff(page_url)
        scorer = HTMLExtractor(page_url)

        # Save candidates
        for candidate in candidates:
            score = scorer.calculate_score(candidate)

            await storage.create_media_candidate(
                sniff_task_id=task_id,
                page_url=page_url,
                media_url=candidate.url,
                media_type=candidate.media_type.value,
                discovery_method=candidate.discovery_method.value,
                source_frame_url=candidate.source_frame_url,
                content_type=candidate.content_type,
                is_temporary=scorer.detect_temporary_url(candidate.url),
                referer=referer,
                user_agent=user_agent,
                title=candidate.title,
                score=score,
            )

        await storage.update_sniff_task(task_id, status="completed")
        await storage.update_sniff_task(task_id, finished_at=datetime.utcnow())

    except Exception as e:
        await storage.update_sniff_task(
            task_id,
            status="failed",
            error_message=str(e),
            finished_at=datetime.utcnow(),
        )


@router.get("/api/sniff/{task_id}", response_model=SniffResultResponse)
async def get_sniff_result(task_id: str):
    """Get sniff task result."""
    task = await storage.get_sniff_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    candidates = await storage.get_candidates_by_sniff_task(task_id)

    return SniffResultResponse(
        task_id=task.id,
        status=TaskStatus(task.status),
        page_url=task.page_url,
        candidates=candidates,
        error_message=task.error_message,
        created_at=task.created_at,
        finished_at=task.finished_at,
    )


@router.post("/api/download", response_model=DownloadResponse)
async def create_download_task(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Create a download task."""
    settings = get_settings()

    # Get candidate
    candidate = await storage.get_media_candidate(request.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Determine output path
    download_dir = request.download_dir or settings.download_dir
    if request.output_name:
        output_path = str(build_safe_output_path(download_dir, request.output_name))
    else:
        # Use page title as filename if available, otherwise use candidate ID
        if candidate.title:
            # Sanitize title for filename: remove invalid chars, limit length
            safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '', candidate.title).strip()
            safe_name = safe_name[:200] if safe_name else None
        else:
            safe_name = None

        if safe_name:
            output_path = str(Path(download_dir) / f"{safe_name}.mp4")
        else:
            short_id = request.candidate_id[-8:]
            output_path = str(Path(download_dir) / f"video_{candidate.media_type}_{short_id}.mp4")

    # Create download task
    media_type = MediaType(candidate.media_type)
    downloader_type = DownloaderType(request.downloader) if request.downloader != "auto" else DownloaderType.AUTO

    task = await storage.create_download_task(
        candidate_id=request.candidate_id,
        url=candidate.media_url,
        downloader=downloader_type.value,
        output_path=output_path,
    )

    # Run download in background
    background_tasks.add_task(
        _run_download_task,
        task.id,
        candidate.media_url,
        media_type,
        output_path,
        downloader_type,
        candidate.referer,
        candidate.user_agent,
        request.concurrency,
    )

    return DownloadResponse(
        download_id=task.id,
        status=TaskStatus.RUNNING,
    )


async def _run_download_task(
    task_id: str,
    url: str,
    media_type: MediaType,
    output_path: str,
    downloader_type: DownloaderType,
    referer: Optional[str],
    user_agent: Optional[str],
    concurrency: int,
):
    """Run download task in background."""
    await storage.update_download_task(task_id, status="running")

    def on_progress(info):
        asyncio.create_task(
            storage.update_download_task(
                task_id,
                status=info.status,
                progress=info.progress,
                speed=info.speed,
                eta=info.eta,
                downloaded_bytes=info.downloaded_bytes,
                total_bytes=info.total_bytes,
            )
        )
        # Build SSE data with segment info for HLS
        sse_data = {
            "progress": info.progress,
            "speed": info.speed,
            "eta": info.eta,
            "status": info.status,
        }
        if info.media_type:
            sse_data["media_type"] = info.media_type
        if info.segment_current is not None:
            sse_data["segment_current"] = info.segment_current
        if info.segment_total is not None:
            sse_data["segment_total"] = info.segment_total
        asyncio.create_task(
            progress_streamer.publish(task_id, json.dumps(sse_data))
        )

    result = await download_manager.start_download(
        task_id=task_id,
        url=url,
        media_type=media_type,
        output_path=output_path,
        downloader_type=downloader_type,
        referer=referer,
        user_agent=user_agent,
        concurrency=concurrency,
        on_progress=on_progress,
    )

    if result.success:
        await storage.update_download_task(
            task_id,
            status="completed",
            output_path=result.output_path,
            progress=100.0,
            finished_at=datetime.utcnow(),
        )
        await progress_streamer.publish(
            task_id,
            json.dumps({
                "progress": 100.0,
                "speed": None,
                "eta": None,
                "status": "completed",
                "output_path": result.output_path,
            }),
        )
    else:
        await storage.update_download_task(
            task_id,
            status="failed",
            error_message=result.error_message,
            finished_at=datetime.utcnow(),
        )
        await progress_streamer.publish(
            task_id,
            json.dumps({
                "progress": 0.0,
                "speed": None,
                "eta": None,
                "status": "failed",
                "error_message": result.error_message,
            }),
        )


@router.get("/api/download/{download_id}", response_model=DownloadProgressResponse)
async def get_download_progress(download_id: str):
    """Get download progress."""
    task = await storage.get_download_task(download_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get real-time segment info from progress tracker
    progress_info = download_manager.get_progress(download_id)
    segment_current = None
    segment_total = None
    media_type = None
    stage = None
    elapsed_seconds = None
    file_size_bytes = None
    logs = None
    if progress_info:
        segment_current = progress_info.segment_current
        segment_total = progress_info.segment_total
        media_type = progress_info.media_type
        stage = progress_info.stage
        elapsed_seconds = progress_info.elapsed_seconds
        file_size_bytes = progress_info.file_size_bytes
        logs = progress_info.logs

    return DownloadProgressResponse(
        download_id=task.id,
        status=TaskStatus(task.status),
        progress=task.progress,
        speed=task.speed,
        eta=task.eta,
        output_path=task.output_path,
        downloaded_bytes=task.downloaded_bytes,
        total_bytes=task.total_bytes,
        error_message=task.error_message,
        media_type=media_type,
        segment_current=segment_current,
        segment_total=segment_total,
        stage=stage,
        elapsed_seconds=elapsed_seconds,
        file_size_bytes=file_size_bytes,
        logs=logs,
    )


@router.get("/api/downloads")
async def get_download_tasks(limit: int = 20):
    """Get recent download tasks so the UI can restore its queue after navigation."""
    active_ids = set(download_manager.get_active_tasks())
    tasks = await storage.get_all_download_tasks(limit=limit)

    stale_statuses = {"pending", "running", "downloading", "merging"}
    for task in tasks:
        if task.status in stale_statuses and task.id not in active_ids:
            await storage.update_download_task(
                task.id,
                status="cancelled",
                error_message="任务未在当前下载进程中运行，已自动清理",
                finished_at=datetime.utcnow(),
            )

    tasks = await storage.get_all_download_tasks(limit=limit)
    active_ids = set(download_manager.get_active_tasks())

    return {
        "items": [
            {
                "download_id": task.id,
                "candidate_id": task.candidate_id,
                "url": task.url,
                "downloader": task.downloader,
                "status": task.status,
                "active": task.id in active_ids,
                "progress": task.progress,
                "speed": task.speed,
                "eta": task.eta,
                "output_path": task.output_path,
                "downloaded_bytes": task.downloaded_bytes,
                "total_bytes": task.total_bytes,
                "error_message": task.error_message,
                "created_at": task.created_at,
                "finished_at": task.finished_at,
            }
            for task in tasks
        ]
    }


@router.get("/api/download/{download_id}/events")
async def download_events(download_id: str):
    """Subscribe to download progress events via SSE."""
    return StreamingResponse(
        progress_streamer.subscribe(download_id),
        media_type="text/event-stream",
    )


@router.delete("/api/download/{download_id}")
async def delete_download_task(download_id: str, cleanup: bool = False):
    """Delete a download task. If cleanup=true, also delete the completed file."""
    task = await storage.get_download_task(download_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # Always clean temp files when deleting task
    _cleanup_download_files(task.output_path)

    success = await storage.delete_history(download_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"status": "deleted"}


def _cleanup_download_files(output_path: str) -> None:
    """Remove downloaded file and all related temp files.

    Cleans:
    - Final output file (video.mp4)
    - yt-dlp temp files (.part, .ytdl, .temp)
    - yt-dlp format-specific parts (video.f1234.part)
    - ffmpeg temp files (.tmp)
    - HLS segment files (.ts)
    - Temp directories created by downloaders
    """
    if not output_path:
        return
    p = Path(output_path)
    if not p.parent.exists():
        return

    parent = p.parent
    stem = p.stem

    # 1. Remove the final output file
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass

    # 2. Remove temp files with common suffixes
    temp_suffixes = [".part", ".ytdl", ".temp", ".tmp", ".ts"]
    for suffix in temp_suffixes:
        for f in parent.glob(f"{stem}*{suffix}*"):
            if f.is_file():
                try:
                    f.unlink()
                except OSError:
                    pass

    # 3. Remove yt-dlp format-specific parts (e.g., video.f1234.video.part)
    for f in parent.glob(f"{stem}.*.part"):
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass

    # 4. Remove yt-dlp format-specific video/audio files (e.g., video.f1234.mp4)
    for f in parent.glob(f"{stem}.f*.mp4"):
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass
    for f in parent.glob(f"{stem}.f*.m4a"):
        if f.is_file():
            try:
                f.unlink()
            except OSError:
                pass

    # 5. Remove temp directories (ffmpeg sometimes creates these)
    for d in parent.glob(f"{stem}_*"):
        if d.is_dir():
            import shutil
            try:
                shutil.rmtree(d)
            except OSError:
                pass

    # 6. Remove ffmpeg concat list files
    for f in parent.glob(f"{stem}*.txt"):
        if f.is_file() and "concat" in f.name.lower():
            try:
                f.unlink()
            except OSError:
                pass


@router.post("/api/open-file")
async def open_file(request: Request):
    """Open a file or directory with the system default application."""
    import subprocess
    import platform

    data = await request.json()
    path = data.get("path", "")

    if not path:
        raise HTTPException(status_code=400, detail="path is required")

    path = str(Path(path).resolve())
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail=f"路径不存在: {path}")

    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", path])
        elif system == "Windows":
            subprocess.Popen(["explorer", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"status": "opened", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/download/{download_id}/cancel")
async def cancel_download(download_id: str):
    """Cancel a download task and clean up all temp files."""
    task = await storage.get_download_task(download_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    success = await download_manager.cancel_download(download_id)

    # Clean up all download files (including partial, segments, etc.)
    _cleanup_download_files(task.output_path)

    if not success and task.status in {"completed", "failed", "cancelled"}:
        return {"status": task.status}

    await storage.update_download_task(
        download_id,
        status="cancelled",
        error_message=None if success else "任务未在当前下载进程中运行，已标记为取消",
        finished_at=datetime.utcnow(),
    )
    return {"status": "cancelled"}


@router.get("/api/history", response_model=HistoryResponse)
async def get_history(
    limit: int = 100,
    status: Optional[str] = None,
):
    """Get download history."""
    items = await storage.get_history(limit=limit, status=status)
    return HistoryResponse(items=items, total=len(items))


@router.get("/api/history/{item_id}")
async def get_history_item(item_id: str):
    """Get a specific history item."""
    task = await storage.get_download_task(item_id)
    if not task:
        raise HTTPException(status_code=404, detail="Item not found")

    candidate = await storage.get_media_candidate(task.candidate_id)

    return {
        "id": task.id,
        "url": task.url,
        "status": task.status,
        "output_path": task.output_path,
        "progress": task.progress,
        "created_at": task.created_at,
        "finished_at": task.finished_at,
        "candidate": {
            "page_url": candidate.page_url if candidate else None,
            "media_type": candidate.media_type if candidate else None,
            "resolution": candidate.resolution if candidate else None,
        } if candidate else None,
    }


@router.delete("/api/history/{item_id}")
async def delete_history_item(item_id: str):
    """Delete a history item."""
    success = await storage.delete_history(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return {"status": "deleted"}


@router.get("/api/config", response_model=ConfigResponse)
async def get_config():
    """Get current configuration."""
    settings = get_settings()
    return ConfigResponse(
        download_dir=settings.download_dir,
        database_path=settings.database_path,
        headless=settings.headless,
        wait_seconds=settings.wait_seconds,
        auto_click=settings.auto_click,
        default_downloader=settings.default_downloader,
        concurrency=settings.concurrency,
        user_agent=settings.user_agent,
    )


@router.put("/api/config")
async def update_config(request: ConfigUpdate):
    """Update configuration and persist to .env file."""
    settings = get_settings()
    env_path = Path(__file__).parent.parent.parent / ".env"

    # Build updated values
    updates = {}
    if request.download_dir is not None:
        updates["VIDEO_FINDER_DOWNLOAD_DIR"] = request.download_dir
    if request.headless is not None:
        updates["VIDEO_FINDER_HEADLESS"] = str(request.headless).lower()
    if request.wait_seconds is not None:
        updates["VIDEO_FINDER_WAIT_SECONDS"] = str(request.wait_seconds)
    if request.auto_click is not None:
        updates["VIDEO_FINDER_AUTO_CLICK"] = str(request.auto_click).lower()
    if request.default_downloader is not None:
        updates["VIDEO_FINDER_DEFAULT_DOWNLOADER"] = request.default_downloader.value
    if request.concurrency is not None:
        updates["VIDEO_FINDER_CONCURRENCY"] = str(request.concurrency)
    if request.user_agent is not None:
        updates["VIDEO_FINDER_USER_AGENT"] = request.user_agent

    # Read existing .env and merge
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    new_lines = []
    updated_keys = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Append any new keys not in the file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Return the merged config (settings + overrides)
    return ConfigResponse(
        download_dir=updates.get("VIDEO_FINDER_DOWNLOAD_DIR", settings.download_dir),
        database_path=settings.database_path,
        headless=updates.get("VIDEO_FINDER_HEADLESS", str(settings.headless)).lower() == "true",
        wait_seconds=int(updates.get("VIDEO_FINDER_WAIT_SECONDS", settings.wait_seconds)),
        auto_click=updates.get("VIDEO_FINDER_AUTO_CLICK", str(settings.auto_click)).lower() == "true",
        default_downloader=updates.get("VIDEO_FINDER_DEFAULT_DOWNLOADER", settings.default_downloader),
        concurrency=int(updates.get("VIDEO_FINDER_CONCURRENCY", settings.concurrency)),
        user_agent=updates.get("VIDEO_FINDER_USER_AGENT", settings.user_agent),
    )


@router.get("/api/check-dependencies")
async def check_dependencies():
    """Check if required dependencies are installed."""
    from ..downloaders.ytdlp import YtdlpProbe
    from ..downloaders.ffmpeg import FFmpegProbe

    ytdlp_probe = YtdlpProbe()
    ffmpeg_probe = FFmpegProbe()

    return {
        "yt_dlp": await ytdlp_probe.check_available(),
        "ffmpeg": await ffmpeg_probe.check_available(),
    }
