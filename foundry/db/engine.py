"""Async SQLAlchemy engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def create_engine(database_url: str) -> tuple:
    """Create an async engine and session factory.

    Args:
        database_url: PostgreSQL connection string (async driver).

    Returns:
        Tuple of (engine, session_factory).
    """
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory
