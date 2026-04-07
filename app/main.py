"""FastAPI application entry point."""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.deps import set_session_factory
from app.routes import batches, evals, health, patches, reviews, runs, specs, worktrees


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown.

    On startup: create the async SQLAlchemy engine and session factory.
    On shutdown: dispose the engine to release connection pool resources.
    """
    settings = Settings()
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
    )
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    set_session_factory(factory)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Unicorn Foundry",
        description="Internal orchestration API for Unicorn Protocol.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- Middleware -----------------------------------------------------------

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: object) -> Response:
        """Attach a unique request ID and measure request duration."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.monotonic()
        response: Response = await call_next(request)  # type: ignore[misc]
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)
        return response

    # --- Routers --------------------------------------------------------------

    app.include_router(health.router, prefix="/v1", tags=["health"])
    app.include_router(runs.router, prefix="/v1", tags=["runs"])
    app.include_router(reviews.router, prefix="/v1", tags=["reviews"])
    app.include_router(specs.router, prefix="/v1", tags=["specs"])
    app.include_router(patches.router, prefix="/v1", tags=["patches"])
    app.include_router(batches.router, prefix="/v1", tags=["batches"])
    app.include_router(evals.router, prefix="/v1", tags=["evals"])
    app.include_router(worktrees.router, prefix="/v1", tags=["worktrees"])

    return app


app = create_app()
