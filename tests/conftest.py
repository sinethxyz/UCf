"""Shared test fixtures for Foundry unit tests."""

import pytest
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from foundry.contracts.shared import MCPProfile, TaskType
from foundry.contracts.task_types import TaskRequest
from foundry.db.models import Base


@pytest.fixture
async def async_session():
    """Yield an async SQLAlchemy session backed by an in-memory SQLite database."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    # SQLite needs foreign key enforcement enabled per-connection.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Render JSONB as JSON for SQLite compatibility in tests.
    @event.listens_for(Base.metadata, "column_reflect")
    def _adapt_jsonb(inspector, table, column_info):
        if isinstance(column_info["type"], JSONB):
            column_info["type"] = JSON()

    # Patch JSONB columns to JSON before creating tables on SQLite.
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()

    # Restore JSONB types so other test sessions get a clean slate.
    # (Metadata is shared across the process, so mutations stick.)
    # In practice each pytest session gets a fresh import, so this is defensive.


@pytest.fixture
def sample_task_request() -> TaskRequest:
    """Return a minimal valid TaskRequest for testing."""
    return TaskRequest(
        task_type=TaskType.BUG_FIX,
        repo="unicorn-app",
        base_branch="main",
        title="Fix pagination bug",
        prompt="Fix the off-by-one error in search pagination",
        mcp_profile=MCPProfile.NONE,
        metadata={"ticket": "UNI-123"},
    )
