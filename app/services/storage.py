"""Storage service for database operations."""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session_factory
from ..models import SniffTask, MediaCandidate, DownloadTask, TaskLog


class StorageService:
    """Storage service for database operations."""

    def __init__(self):
        self._session_factory = get_session_factory()

    def _generate_id(self, prefix: str = "") -> str:
        """Generate unique ID."""
        return f"{prefix}{uuid.uuid4().hex[:12]}"

    # Sniff Task Operations

    async def create_sniff_task(
        self,
        page_url: str,
        wait_seconds: int = 10,
        auto_click: bool = True,
        headless: bool = True,
        user_agent: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> SniffTask:
        """Create a new sniff task."""
        task = SniffTask(
            id=self._generate_id("sniff_"),
            page_url=page_url,
            status="pending",
            wait_seconds=wait_seconds,
            auto_click=auto_click,
            headless=headless,
            user_agent=user_agent,
            referer=referer,
            created_at=datetime.utcnow(),
        )
        async with self._session_factory() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)
        return task

    async def update_sniff_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        finished_at: Optional[datetime] = None,
    ) -> Optional[SniffTask]:
        """Update sniff task status."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(SniffTask).where(SniffTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if task:
                if status:
                    task.status = status
                if error_message is not None:
                    task.error_message = error_message
                if finished_at:
                    task.finished_at = finished_at
                await session.commit()
                await session.refresh(task)
            return task

    async def get_sniff_task(self, task_id: str) -> Optional[SniffTask]:
        """Get sniff task by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(SniffTask).where(SniffTask.id == task_id)
            )
            return result.scalar_one_or_none()

    # Media Candidate Operations

    async def create_media_candidate(
        self,
        sniff_task_id: str,
        page_url: str,
        media_url: str,
        media_type: str,
        discovery_method: str,
        source_frame_url: Optional[str] = None,
        content_type: Optional[str] = None,
        http_status: Optional[int] = None,
        referer: Optional[str] = None,
        user_agent: Optional[str] = None,
        title: Optional[str] = None,
        resolution: Optional[str] = None,
        bandwidth: Optional[int] = None,
        filesize: Optional[int] = None,
        is_temporary: bool = False,
        score: int = 0,
        raw_info_json: Optional[str] = None,
    ) -> MediaCandidate:
        """Create a new media candidate."""
        candidate = MediaCandidate(
            id=self._generate_id("media_"),
            sniff_task_id=sniff_task_id,
            page_url=page_url,
            media_url=media_url,
            media_type=media_type,
            discovery_method=discovery_method,
            source_frame_url=source_frame_url,
            content_type=content_type,
            http_status=http_status,
            referer=referer,
            user_agent=user_agent,
            title=title,
            resolution=resolution,
            bandwidth=bandwidth,
            filesize=filesize,
            is_temporary=is_temporary,
            score=score,
            raw_info_json=raw_info_json,
            created_at=datetime.utcnow(),
        )
        async with self._session_factory() as session:
            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)
        return candidate

    async def get_candidates_by_sniff_task(self, sniff_task_id: str) -> list[MediaCandidate]:
        """Get all candidates for a sniff task."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MediaCandidate)
                .where(MediaCandidate.sniff_task_id == sniff_task_id)
                .order_by(MediaCandidate.score.desc())
            )
            return list(result.scalars().all())

    async def get_media_candidate(self, candidate_id: str) -> Optional[MediaCandidate]:
        """Get media candidate by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MediaCandidate).where(MediaCandidate.id == candidate_id)
            )
            return result.scalar_one_or_none()

    # Download Task Operations

    async def create_download_task(
        self,
        candidate_id: str,
        url: str,
        downloader: str,
        output_path: Optional[str] = None,
    ) -> DownloadTask:
        """Create a new download task."""
        task = DownloadTask(
            id=self._generate_id("download_"),
            candidate_id=candidate_id,
            url=url,
            downloader=downloader,
            status="pending",
            output_path=output_path,
            progress=0.0,
            created_at=datetime.utcnow(),
        )
        async with self._session_factory() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)
        return task

    async def update_download_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        speed: Optional[str] = None,
        eta: Optional[str] = None,
        output_path: Optional[str] = None,
        downloaded_bytes: Optional[int] = None,
        total_bytes: Optional[int] = None,
        error_message: Optional[str] = None,
        finished_at: Optional[datetime] = None,
    ) -> Optional[DownloadTask]:
        """Update download task."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(DownloadTask).where(DownloadTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if task:
                if status:
                    task.status = status
                if progress is not None:
                    task.progress = progress
                if speed is not None:
                    task.speed = speed
                if eta is not None:
                    task.eta = eta
                if output_path is not None:
                    task.output_path = output_path
                if downloaded_bytes is not None:
                    task.downloaded_bytes = downloaded_bytes
                if total_bytes is not None:
                    task.total_bytes = total_bytes
                if error_message is not None:
                    task.error_message = error_message
                if finished_at:
                    task.finished_at = finished_at
                await session.commit()
                await session.refresh(task)
            return task

    async def get_download_task(self, task_id: str) -> Optional[DownloadTask]:
        """Get download task by ID."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(DownloadTask).where(DownloadTask.id == task_id)
            )
            return result.scalar_one_or_none()

    async def get_all_download_tasks(self, limit: int = 100) -> list[DownloadTask]:
        """Get all download tasks."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(DownloadTask)
                .order_by(DownloadTask.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    # Task Log Operations

    async def add_task_log(
        self,
        task_id: str,
        task_type: str,
        level: str,
        message: str,
    ) -> TaskLog:
        """Add a task log entry."""
        log = TaskLog(
            id=self._generate_id("log_"),
            task_id=task_id,
            task_type=task_type,
            level=level,
            message=message,
            created_at=datetime.utcnow(),
        )
        async with self._session_factory() as session:
            session.add(log)
            await session.commit()
            await session.refresh(log)
        return log

    async def get_task_logs(self, task_id: str) -> list[TaskLog]:
        """Get logs for a task."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskLog)
                .where(TaskLog.task_id == task_id)
                .order_by(TaskLog.created_at)
            )
            return list(result.scalars().all())

    # History Operations

    async def get_history(self, limit: int = 100, status: Optional[str] = None) -> list[dict]:
        """Get download history."""
        async with self._session_factory() as session:
            query = (
                select(DownloadTask, MediaCandidate)
                .join(MediaCandidate, DownloadTask.candidate_id == MediaCandidate.id)
                .order_by(DownloadTask.created_at.desc())
                .limit(limit)
            )
            if status:
                query = query.where(DownloadTask.status == status)

            result = await session.execute(query)
            history = []
            for task, candidate in result:
                history.append({
                    "id": task.id,
                    "page_url": candidate.page_url,
                    "status": task.status,
                    "media_type": candidate.media_type,
                    "resolution": candidate.resolution,
                    "output_path": task.output_path,
                    "created_at": task.created_at,
                    "finished_at": task.finished_at,
                })
            return history

    async def delete_history(self, task_id: str) -> bool:
        """Delete a download task and its logs."""
        async with self._session_factory() as session:
            # Delete logs first
            await session.execute(
                delete(TaskLog).where(TaskLog.task_id == task_id)
            )
            # Delete task
            result = await session.execute(
                delete(DownloadTask).where(DownloadTask.id == task_id)
            )
            await session.commit()
            return result.rowcount > 0
