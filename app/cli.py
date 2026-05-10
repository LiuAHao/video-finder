"""CLI entry point for video-finder."""

import asyncio
import json
from typing import Optional
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from .config import get_settings
from .schemas import MediaType, DiscoveryMethod, DownloaderType
from .services.sniffer import Sniffer
from .services.extractor import ExtractedResource, HTMLExtractor
from .services.downloader import DownloadManager
from .services.storage import StorageService
from .services.safety import SafetyService, build_safe_output_path
from .downloaders.ytdlp import YtdlpProbe
from .db.database import init_db

app = typer.Typer(
    name="video-finder",
    help="Video Finder - video discovery and download tool",
    add_completion=False,
)
console = Console()


@app.command()
def sniff(
    url: str = typer.Argument(..., help="Page URL to sniff"),
    wait: int = typer.Option(10, "--wait", "-w", help="Wait time in seconds"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    auto_click: bool = typer.Option(True, "--auto-click/--no-auto-click", help="Auto click play button"),
    user_agent: Optional[str] = typer.Option(None, "--user-agent", "-ua", help="Custom User-Agent"),
    referer: Optional[str] = typer.Option(None, "--referer", "-r", help="Custom Referer"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Sniff a page for video resources."""
    asyncio.run(_sniff(url, wait, headless, auto_click, user_agent, referer, json_output))


async def _sniff(
    url: str,
    wait: int,
    headless: bool,
    auto_click: bool,
    user_agent: Optional[str],
    referer: Optional[str],
    json_output: bool,
):
    """Async sniff implementation."""
    settings = get_settings()
    settings.ensure_directories()

    # Initialize database
    await init_db()

    storage = StorageService()
    safety = SafetyService()

    # Create sniff task
    task = await storage.create_sniff_task(
        page_url=url,
        wait_seconds=wait,
        auto_click=auto_click,
        headless=headless,
        user_agent=user_agent,
        referer=referer,
    )

    console.print(f"[bold blue]Starting sniff for:[/bold blue] {url}")
    console.print(f"[dim]Task ID: {task.id}[/dim]")

    # Update task status
    await storage.update_sniff_task(task.id, status="running")

    # Create sniffer
    sniffer = Sniffer(
        headless=headless,
        wait_seconds=wait,
        auto_click=auto_click,
        user_agent=user_agent,
        referer=referer,
        on_progress=lambda msg: console.print(f"[dim]{msg}[/dim]"),
    )

    try:
        # Run sniff
        candidates = await sniffer.sniff(url)

        # Update task status
        await storage.update_sniff_task(
            task.id,
            status="completed",
            finished_at=datetime.utcnow(),
        )

        # Save candidates
        scorer = HTMLExtractor(url)
        saved_candidates = []
        for candidate in candidates:
            score = scorer.calculate_score(candidate)

            saved = await storage.create_media_candidate(
                sniff_task_id=task.id,
                page_url=url,
                media_url=candidate.url,
                media_type=candidate.media_type.value,
                discovery_method=candidate.discovery_method.value,
                source_frame_url=candidate.source_frame_url,
                content_type=candidate.content_type,
                referer=referer,
                user_agent=user_agent,
                is_temporary=scorer.detect_temporary_url(candidate.url),
                score=score,
            )
            saved_candidates.append(saved)

        # Sort by score
        saved_candidates.sort(key=lambda c: c.score, reverse=True)

        if json_output:
            # Output as JSON
            output = {
                "task_id": task.id,
                "status": "completed",
                "candidates": [
                    {
                        "id": c.id,
                        "media_url": c.media_url,
                        "media_type": c.media_type,
                        "discovery_method": c.discovery_method,
                        "resolution": c.resolution,
                        "score": c.score,
                    }
                    for c in saved_candidates
                ],
            }
            console.print(json.dumps(output, indent=2))
        else:
            # Output as table
            if not saved_candidates:
                console.print("[yellow]No candidates found.[/yellow]")
                console.print("[dim]Try increasing wait time or disabling headless mode.[/dim]")
            else:
                console.print(f"\n[bold green]Found {len(saved_candidates)} candidates:[/bold green]\n")

                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("#", style="dim", width=4)
                table.add_column("Type", width=12)
                table.add_column("Method", width=10)
                table.add_column("Resolution", width=10)
                table.add_column("URL", min_width=50)

                for i, candidate in enumerate(saved_candidates, 1):
                    table.add_row(
                        str(i),
                        candidate.media_type,
                        candidate.discovery_method,
                        candidate.resolution or "-",
                        candidate.media_url[:80] + "..." if len(candidate.media_url) > 80 else candidate.media_url,
                    )

                console.print(table)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        await storage.update_sniff_task(
            task.id,
            status="failed",
            error_message=str(e),
            finished_at=datetime.utcnow(),
        )


@app.command()
def download(
    url: str = typer.Argument(..., help="Page URL or direct video URL"),
    select: Optional[int] = typer.Option(None, "--select", "-s", help="Select candidate by number"),
    downloader: str = typer.Option("auto", "--downloader", "-d", help="Downloader: auto, ytdlp, ffmpeg, http"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output filename"),
    dir: Optional[str] = typer.Option(None, "--dir", help="Download directory"),
    format_spec: Optional[str] = typer.Option(None, "--format", "-f", help="Format specification"),
    concurrency: int = typer.Option(8, "--concurrency", "-c", help="Concurrent connections"),
    referer: Optional[str] = typer.Option(None, "--referer", "-r", help="Custom Referer"),
    user_agent: Optional[str] = typer.Option(None, "--user-agent", "-ua", help="Custom User-Agent"),
):
    """Download a video from URL."""
    asyncio.run(_download(url, select, downloader, output, dir, format_spec, concurrency, referer, user_agent))


async def _download(
    url: str,
    select: Optional[int],
    downloader: str,
    output: Optional[str],
    dir: Optional[str],
    format_spec: Optional[str],
    concurrency: int,
    referer: Optional[str],
    user_agent: Optional[str],
):
    """Async download implementation."""
    settings = get_settings()
    settings.ensure_directories()

    # Initialize database
    await init_db()

    storage = StorageService()
    download_manager = DownloadManager()

    download_dir = dir or settings.download_dir
    downloader_type = DownloaderType(downloader)

    # If URL is a direct video link, download directly
    if _is_direct_url(url):
        await _download_direct(
            url=url,
            output=output,
            download_dir=download_dir,
            downloader_type=downloader_type,
            concurrency=concurrency,
            referer=referer,
            user_agent=user_agent,
        )
        return

    # Otherwise, sniff first
    console.print(f"[bold blue]Sniffing page:[/bold blue] {url}")

    sniffer = Sniffer(
        headless=settings.headless,
        wait_seconds=settings.wait_seconds,
        auto_click=settings.auto_click,
        user_agent=user_agent or settings.user_agent,
        referer=referer,
        on_progress=lambda msg: console.print(f"[dim]{msg}[/dim]"),
    )

    try:
        candidates = await sniffer.sniff(url)

        if not candidates:
            console.print("[yellow]No candidates found.[/yellow]")
            return

        # Sort candidates
        candidates.sort(key=lambda c: c.media_type.value, reverse=True)

        # Select candidate
        if select is not None:
            if 1 <= select <= len(candidates):
                selected = candidates[select - 1]
            else:
                console.print(f"[red]Invalid selection: {select}[/red]")
                return
        elif len(candidates) == 1:
            selected = candidates[0]
        else:
            # Show candidates and ask user to select
            console.print(f"\n[bold green]Found {len(candidates)} candidates:[/bold green]\n")

            for i, candidate in enumerate(candidates, 1):
                console.print(f"  {i}. [{candidate.media_type.value}] {candidate.url[:80]}...")

            console.print("\n")
            choice = typer.prompt("Select candidate number", type=int)
            if 1 <= choice <= len(candidates):
                selected = candidates[choice - 1]
            else:
                console.print(f"[red]Invalid selection: {choice}[/red]")
                return

        # Determine output path
        if output:
            output_path = str(build_safe_output_path(download_dir, output))
        else:
            output_path = str(Path(download_dir) / f"video_{selected.media_type.value}.mp4")

        console.print(f"\n[bold blue]Downloading:[/bold blue] {selected.url}")
        console.print(f"[dim]Output: {output_path}[/dim]")

        # Start download
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Downloading...", total=100)

            def on_progress_update(info):
                progress.update(task, completed=info.progress)

            # Create storage task
            storage_task = await storage.create_download_task(
                candidate_id="direct",
                url=selected.url,
                downloader=downloader_type.value,
                output_path=output_path,
            )

            result = await download_manager.start_download(
                task_id=storage_task.id,
                url=selected.url,
                media_type=selected.media_type,
                output_path=output_path,
                downloader_type=downloader_type,
                referer=referer or selected.source_frame_url,
                user_agent=user_agent or settings.user_agent,
                concurrency=concurrency,
                on_progress=on_progress_update,
            )

            if result.success:
                await storage.update_download_task(
                    storage_task.id,
                    status="completed",
                    output_path=result.output_path,
                    progress=100.0,
                    finished_at=datetime.utcnow(),
                )
                console.print(f"\n[bold green]Download completed![/bold green]")
                console.print(f"[dim]File: {result.output_path}[/dim]")
                if result.file_size:
                    size_mb = result.file_size / (1024 * 1024)
                    console.print(f"[dim]Size: {size_mb:.2f} MB[/dim]")
            else:
                await storage.update_download_task(
                    storage_task.id,
                    status="failed",
                    error_message=result.error_message,
                    finished_at=datetime.utcnow(),
                )
                console.print(f"\n[bold red]Download failed:[/bold red] {result.error_message}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


async def _download_direct(
    url: str,
    output: Optional[str],
    download_dir: str,
    downloader_type: DownloaderType,
    concurrency: int,
    referer: Optional[str],
    user_agent: Optional[str],
):
    """Download a direct URL."""
    settings = get_settings()
    download_manager = DownloadManager()
    storage = StorageService()

    # Determine output path
    if output:
        output_path = str(build_safe_output_path(download_dir, output))
    else:
        from .downloaders.http import HttpDownloader
        filename = HttpDownloader.get_filename_from_url(url)
        output_path = str(Path(download_dir) / filename)

    console.print(f"[bold blue]Downloading:[/bold blue] {url}")
    console.print(f"[dim]Output: {output_path}[/dim]")

    # Create storage task
    storage_task = await storage.create_download_task(
        candidate_id="direct",
        url=url,
        downloader=downloader_type.value,
        output_path=output_path,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading...", total=100)

        result = await download_manager.start_download(
            task_id=storage_task.id,
            url=url,
            media_type=MediaType.DIRECT_VIDEO,
            output_path=output_path,
            downloader_type=downloader_type,
            referer=referer,
            user_agent=user_agent or settings.user_agent,
            concurrency=concurrency,
            on_progress=lambda info: progress.update(task, completed=info.progress),
        )

        if result.success:
            await storage.update_download_task(
                storage_task.id,
                status="completed",
                output_path=result.output_path,
                progress=100.0,
                finished_at=datetime.utcnow(),
            )
            progress.update(task, completed=100)
            console.print(f"\n[bold green]Download completed![/bold green]")
            console.print(f"[dim]File: {result.output_path}[/dim]")
            if result.file_size:
                size_mb = result.file_size / (1024 * 1024)
                console.print(f"[dim]Size: {size_mb:.2f} MB[/dim]")
        else:
            await storage.update_download_task(
                storage_task.id,
                status="failed",
                error_message=result.error_message,
                finished_at=datetime.utcnow(),
            )
            console.print(f"\n[bold red]Download failed:[/bold red] {result.error_message}")


def _is_direct_url(url: str) -> bool:
    """Check if URL is a direct video link."""
    from .constants import VIDEO_EXTENSIONS, HLS_EXTENSIONS, DASH_EXTENSIONS
    parsed = urlparse(url.lower())
    path = parsed.path
    return any(
        path.endswith(ext)
        for ext in VIDEO_EXTENSIONS | HLS_EXTENSIONS | DASH_EXTENSIONS
    )


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of records"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show download history."""
    asyncio.run(_history(limit, status, json_output))


async def _history(limit: int, status: Optional[str], json_output: bool):
    """Async history implementation."""
    settings = get_settings()
    settings.ensure_directories()

    # Initialize database
    await init_db()

    storage = StorageService()

    history_items = await storage.get_history(limit=limit, status=status)

    if json_output:
        output = [
            {
                "id": item["id"],
                "page_url": item["page_url"],
                "status": item["status"],
                "media_type": item["media_type"],
                "output_path": item["output_path"],
                "created_at": item["created_at"].isoformat() if item["created_at"] else None,
            }
            for item in history_items
        ]
        console.print(json.dumps(output, indent=2))
    else:
        if not history_items:
            console.print("[yellow]No history found.[/yellow]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=15)
        table.add_column("Status", width=12)
        table.add_column("Type", width=10)
        table.add_column("URL", min_width=40)
        table.add_column("Output", min_width=30)
        table.add_column("Time", width=20)

        for item in history_items:
            table.add_row(
                item["id"],
                item["status"],
                item["media_type"] or "-",
                item["page_url"][:50] + "..." if len(item["page_url"]) > 50 else item["page_url"],
                item["output_path"] or "-",
                item["created_at"].strftime("%Y-%m-%d %H:%M") if item["created_at"] else "-",
            )

        console.print(table)


@app.command(name="open")
def open_web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Server host"),
    port: int = typer.Option(7860, "--port", "-p", help="Server port"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
):
    """Start web interface."""
    import webbrowser
    from .main import run_server

    if not no_browser:
        webbrowser.open(f"http://{host}:{port}")

    run_server(host=host, port=port)


@app.command()
def config():
    """Show current configuration."""
    settings = get_settings()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="dim")
    table.add_column("Value")

    table.add_row("Download Directory", settings.download_dir)
    table.add_row("Database Path", settings.database_path)
    table.add_row("Headless Mode", str(settings.headless))
    table.add_row("Wait Seconds", str(settings.wait_seconds))
    table.add_row("Auto Click", str(settings.auto_click))
    table.add_row("Default Downloader", settings.default_downloader)
    table.add_row("Concurrency", str(settings.concurrency))
    table.add_row("User-Agent", settings.user_agent[:50] + "...")

    console.print(table)


if __name__ == "__main__":
    app()
