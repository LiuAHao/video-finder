"""Database connection and initialization."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import get_settings
from ..models import Base


# Async engine
engine = None
async_session_factory = None


def get_engine():
    """Get or create async engine."""
    global engine
    if engine is None:
        settings = get_settings()
        db_path = settings.database_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            future=True,
        )
    return engine


def get_session_factory():
    """Get or create async session factory."""
    global async_session_factory
    if async_session_factory is None:
        async_session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return async_session_factory


async def get_session() -> AsyncSession:
    """Get async database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db():
    """Initialize database tables."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connection."""
    global engine, async_session_factory
    if engine:
        await engine.dispose()
        engine = None
        async_session_factory = None
