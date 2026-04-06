"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Foundry application settings."""

    database_url: str = "postgresql+asyncpg://foundry:foundry@localhost:5432/foundry"
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str = ""
    github_token: str = ""
    artifact_storage_path: str = "artifacts"
    worktree_base_path: str = "/tmp/foundry-worktrees"
    log_level: str = "INFO"

    model_config = {"env_prefix": "FOUNDRY_"}


settings = Settings()
