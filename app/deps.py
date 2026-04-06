"""Dependency injection for FastAPI route handlers."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from foundry.db.engine import create_engine

_engine, _session_factory = create_engine(settings.database_url)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session."""
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
