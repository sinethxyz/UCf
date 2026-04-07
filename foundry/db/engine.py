"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(database_url: str) -> AsyncEngine:
    """Create an async SQLAlchemy engine backed by asyncpg.

    Args:
        database_url: PostgreSQL connection string using the asyncpg driver
                      (e.g. ``postgresql+asyncpg://user:pass@host/db``).

    Returns:
        The configured AsyncEngine instance.
    """
    global _engine, _session_factory
    _engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session.

    Must be called after :func:`create_engine`.  The session is committed on
    successful exit and rolled back on exception.

    Yields:
        An ``AsyncSession`` bound to the configured engine.

    Raises:
        RuntimeError: If called before ``create_engine``.
    """
    if _session_factory is None:
        raise RuntimeError("Database engine not initialised — call create_engine() first")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
