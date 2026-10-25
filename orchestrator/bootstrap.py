from pathlib import Path

from app.core.config import Settings
from orchestrator.engine import WorkflowEngine
from orchestrator.providers.deterministic import DeterministicProvider
from orchestrator.providers.openai_compatible import OpenAICompatibleProvider
from orchestrator.store import WorkflowStore
from orchestrator.test_runner import PytestRunner


def build_engine(settings: Settings) -> WorkflowEngine:
    """Wire the engine from settings. The deterministic provider is the default and fallback."""
    fallback = DeterministicProvider()
    if settings.ai_provider.lower() == "openai" and settings.openai_api_key:
        provider = OpenAICompatibleProvider(settings.openai_api_key, settings.openai_model)
    else:
        provider = fallback
    return WorkflowEngine(
        store=WorkflowStore(settings.workflow_database_url),
        workspace_root=Path(settings.workspace_root),
        repo_root=Path(settings.repo_root),
        provider=provider,
        fallback_provider=fallback,
        test_runner=PytestRunner(settings.test_timeout_seconds),
        max_retries=settings.max_retries,
        retry_backoff_ms=settings.retry_backoff_ms,
        max_parallel_tasks=settings.max_parallel_tasks,
        allow_fault_injection=settings.allow_fault_injection,
    )
