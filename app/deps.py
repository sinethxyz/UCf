"""Dependency injection for FastAPI route handlers."""

from collections.abc import AsyncGenerator
from functools import lru_cache

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from foundry.git.pr import PRCreator
from foundry.git.worktree import WorktreeManager
from foundry.orchestration.agent_runner import AgentRunner
from foundry.orchestration.run_engine import RunEngine
from foundry.storage.artifact_store import ArtifactStore
from foundry.verification.runner import VerificationRunner


_session_factory: async_sessionmaker[AsyncSession] | None = None
_redis_pool: aioredis.Redis | None = None


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


async def get_redis() -> aioredis.Redis:
    """Return a shared Redis connection."""
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_pool


async def get_run_engine(
    session: AsyncSession,
) -> RunEngine:
    """Build a RunEngine with all dependencies injected."""
    settings = get_settings()
    return RunEngine(
        session=session,
        artifact_store=get_artifact_store(),
        worktree_manager=WorktreeManager(
            repo_path=".",
            worktree_base=settings.worktree_base_path,
        ),
        agent_runner=AgentRunner(),
        pr_creator=PRCreator(),
        verification_runner=VerificationRunner(),
    )
