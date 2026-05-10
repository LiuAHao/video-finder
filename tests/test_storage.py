"""Tests for storage module."""

import pytest
import pytest_asyncio
from unittest.mock import patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.models import Base
from app.services.storage import StorageService


@pytest_asyncio.fixture
async def storage():
    """Create a StorageService with in-memory SQLite."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    with patch("app.services.storage.get_session_factory", return_value=session_factory):
        svc = StorageService()
        yield svc

    await engine.dispose()


class TestSniffTaskCRUD:
    """Test SniffTask create/read/update."""

    @pytest.mark.asyncio
    async def test_create_sniff_task(self, storage: StorageService):
        task = await storage.create_sniff_task(
            page_url="https://example.com/video",
            wait_seconds=15,
            auto_click=True,
            headless=False,
        )
        assert task.id.startswith("sniff_")
        assert task.page_url == "https://example.com/video"
        assert task.status == "pending"
        assert task.wait_seconds == 15
        assert task.headless is False

    @pytest.mark.asyncio
    async def test_get_sniff_task(self, storage: StorageService):
        created = await storage.create_sniff_task(page_url="https://example.com")
        fetched = await storage.get_sniff_task(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.page_url == "https://example.com"

    @pytest.mark.asyncio
    async def test_get_sniff_task_nonexistent(self, storage: StorageService):
        assert await storage.get_sniff_task("nonexistent") is None

    @pytest.mark.asyncio
    async def test_update_sniff_task_status(self, storage: StorageService):
        task = await storage.create_sniff_task(page_url="https://example.com")
        updated = await storage.update_sniff_task(
            task.id, status="completed", finished_at=task.created_at
        )
        assert updated is not None
        assert updated.status == "completed"

    @pytest.mark.asyncio
    async def test_update_sniff_task_error(self, storage: StorageService):
        task = await storage.create_sniff_task(page_url="https://example.com")
        updated = await storage.update_sniff_task(
            task.id, status="failed", error_message="timeout"
        )
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error_message == "timeout"

    @pytest.mark.asyncio
    async def test_update_nonexistent_task(self, storage: StorageService):
        result = await storage.update_sniff_task("nonexistent", status="completed")
        assert result is None


class TestMediaCandidateCRUD:
    """Test MediaCandidate create/read."""

    @pytest.mark.asyncio
    async def test_create_candidate(self, storage: StorageService):
        task = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=task.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/video.m3u8",
            media_type="hls",
            discovery_method="network",
            score=95,
        )
        assert candidate.id.startswith("media_")
        assert candidate.media_type == "hls"
        assert candidate.score == 95

    @pytest.mark.asyncio
    async def test_get_candidates_by_sniff_task(self, storage: StorageService):
        task = await storage.create_sniff_task(page_url="https://example.com")
        await storage.create_media_candidate(
            sniff_task_id=task.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/a.m3u8",
            media_type="hls",
            discovery_method="network",
            score=90,
        )
        await storage.create_media_candidate(
            sniff_task_id=task.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/b.mp4",
            media_type="direct_video",
            discovery_method="html",
            score=80,
        )
        candidates = await storage.get_candidates_by_sniff_task(task.id)
        assert len(candidates) == 2
        # Should be ordered by score desc
        assert candidates[0].score >= candidates[1].score

    @pytest.mark.asyncio
    async def test_get_candidates_empty(self, storage: StorageService):
        candidates = await storage.get_candidates_by_sniff_task("nonexistent")
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_get_media_candidate(self, storage: StorageService):
        task = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=task.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/video.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        fetched = await storage.get_media_candidate(candidate.id)
        assert fetched is not None
        assert fetched.id == candidate.id

    @pytest.mark.asyncio
    async def test_get_media_candidate_nonexistent(self, storage: StorageService):
        assert await storage.get_media_candidate("nonexistent") is None


class TestDownloadTaskCRUD:
    """Test DownloadTask create/read/update."""

    @pytest.mark.asyncio
    async def test_create_download_task(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        dl = await storage.create_download_task(
            candidate_id=candidate.id,
            url="https://cdn.example.com/v.mp4",
            downloader="ytdlp",
        )
        assert dl.id.startswith("download_")
        assert dl.status == "pending"
        assert dl.downloader == "ytdlp"

    @pytest.mark.asyncio
    async def test_get_download_task(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        dl = await storage.create_download_task(
            candidate_id=candidate.id,
            url="https://cdn.example.com/v.mp4",
            downloader="http",
        )
        fetched = await storage.get_download_task(dl.id)
        assert fetched is not None
        assert fetched.id == dl.id

    @pytest.mark.asyncio
    async def test_update_download_progress(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        dl = await storage.create_download_task(
            candidate_id=candidate.id,
            url="https://cdn.example.com/v.mp4",
            downloader="http",
        )
        updated = await storage.update_download_task(
            dl.id,
            status="downloading",
            progress=50.0,
            speed="1.5MiB/s",
            eta="00:30",
            downloaded_bytes=5000,
            total_bytes=10000,
        )
        assert updated is not None
        assert updated.status == "downloading"
        assert updated.progress == 50.0
        assert updated.speed == "1.5MiB/s"

    @pytest.mark.asyncio
    async def test_update_download_completed(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        dl = await storage.create_download_task(
            candidate_id=candidate.id,
            url="https://cdn.example.com/v.mp4",
            downloader="http",
        )
        updated = await storage.update_download_task(
            dl.id, status="completed", progress=100.0
        )
        assert updated.status == "completed"
        assert updated.progress == 100.0

    @pytest.mark.asyncio
    async def test_get_all_download_tasks(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        for i in range(3):
            await storage.create_download_task(
                candidate_id=candidate.id,
                url=f"https://cdn.example.com/v{i}.mp4",
                downloader="http",
            )
        tasks = await storage.get_all_download_tasks()
        assert len(tasks) == 3


class TestTaskLogOperations:
    """Test TaskLog create/read."""

    @pytest.mark.asyncio
    async def test_add_and_get_logs(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        dl = await storage.create_download_task(
            candidate_id=candidate.id,
            url="https://cdn.example.com/v.mp4",
            downloader="http",
        )
        await storage.add_task_log(dl.id, "download", "info", "started")
        await storage.add_task_log(dl.id, "download", "info", "50% done")
        await storage.add_task_log(dl.id, "download", "info", "completed")

        logs = await storage.get_task_logs(dl.id)
        assert len(logs) == 3
        assert logs[0].message == "started"
        assert logs[2].message == "completed"

    @pytest.mark.asyncio
    async def test_get_logs_empty(self, storage: StorageService):
        logs = await storage.get_task_logs("nonexistent")
        assert len(logs) == 0


class TestHistoryOperations:
    """Test history query and delete."""

    @pytest.mark.asyncio
    async def test_get_history(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
            resolution="1080p",
        )
        dl = await storage.create_download_task(
            candidate_id=candidate.id,
            url="https://cdn.example.com/v.mp4",
            downloader="http",
        )
        await storage.update_download_task(dl.id, status="completed")

        history = await storage.get_history()
        assert len(history) == 1
        assert history[0]["page_url"] == "https://example.com"
        assert history[0]["status"] == "completed"
        assert history[0]["resolution"] == "1080p"

    @pytest.mark.asyncio
    async def test_get_history_with_status_filter(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        dl1 = await storage.create_download_task(
            candidate_id=candidate.id, url="https://a.mp4", downloader="http"
        )
        dl2 = await storage.create_download_task(
            candidate_id=candidate.id, url="https://b.mp4", downloader="http"
        )
        await storage.update_download_task(dl1.id, status="completed")
        await storage.update_download_task(dl2.id, status="failed")

        completed = await storage.get_history(status="completed")
        assert len(completed) == 1
        failed = await storage.get_history(status="failed")
        assert len(failed) == 1

    @pytest.mark.asyncio
    async def test_delete_history(self, storage: StorageService):
        sniff = await storage.create_sniff_task(page_url="https://example.com")
        candidate = await storage.create_media_candidate(
            sniff_task_id=sniff.id,
            page_url="https://example.com",
            media_url="https://cdn.example.com/v.mp4",
            media_type="direct_video",
            discovery_method="html",
        )
        dl = await storage.create_download_task(
            candidate_id=candidate.id, url="https://a.mp4", downloader="http"
        )
        await storage.add_task_log(dl.id, "download", "info", "test log")

        deleted = await storage.delete_history(dl.id)
        assert deleted is True

        # Verify task is gone
        assert await storage.get_download_task(dl.id) is None
        # Verify logs are gone
        logs = await storage.get_task_logs(dl.id)
        assert len(logs) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_history(self, storage: StorageService):
        deleted = await storage.delete_history("nonexistent")
        assert deleted is False
