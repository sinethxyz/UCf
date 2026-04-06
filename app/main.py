"""FastAPI application entry point."""

from fastapi import FastAPI

from app.routes import batches, evals, health, patches, reviews, runs, specs, worktrees


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Unicorn Foundry",
        description="Internal orchestration API for Unicorn Protocol.",
        version="0.1.0",
    )

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
