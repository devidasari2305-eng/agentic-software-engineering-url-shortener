from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/urlshortener.db"
    workflow_database_url: str = "sqlite:///./data/workflows.db"
    workspace_root: str = "./workspaces"
    repo_root: str = str(PROJECT_ROOT)
    base_url: str = "http://localhost:8000"

    max_retries: int = 2
    retry_backoff_ms: int = 0
    max_parallel_tasks: int = 4
    test_timeout_seconds: int = 120
    allow_fault_injection: bool = True

    ai_provider: str = "deterministic"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
