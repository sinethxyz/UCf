"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Foundry application settings.

    All values can be overridden via environment variables prefixed with
    ``FOUNDRY_`` (e.g. ``FOUNDRY_DATABASE_URL``).
    """

    database_url: str = "postgresql+asyncpg://foundry:foundry@localhost:5432/foundry"
    redis_url: str = "redis://localhost:6379"
    github_token: str = ""
    anthropic_api_key: str = ""
    object_storage_bucket: str = "unicorn-foundry-artifacts"
    foundry_db_url: str = "postgresql+asyncpg://foundry:foundry@localhost:5432/foundry"
    unicorn_app_internal_url: str = "http://localhost:8080"
    max_concurrent_runs: int = 5
    max_retries_per_run: int = 3
    worktree_base_path: str = "/tmp/foundry-worktrees"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FOUNDRY_")
