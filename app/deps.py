"""Dependency injection for FastAPI route handlers."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from foundry.orchestration.run_engine import RunEngine
from foundry.storage.artifact_store import ArtifactStore


_session_factory: async_sessionmaker[AsyncSession] | None = None


def set_session_factory(factory: async_sessionmaker[AsyncSession]) -> None:
    """Set the global session factory (called during app lifespan)."""
    global _session_factory
    _session_factory = factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, committing on success."""
    if _session_factory is None:
        raise RuntimeError("Database engine not initialised — app lifespan not started")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


def get_artifact_store() -> ArtifactStore:
    """Return an ArtifactStore configured from settings."""
    settings = get_settings()
    return ArtifactStore(base_path=settings.object_storage_bucket)


def get_run_engine() -> RunEngine:
    """Return a RunEngine instance."""
    return RunEngine()
