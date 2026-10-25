import os
import tempfile
from pathlib import Path

import pytest

# Isolate every database and workspace from the developer's real data *before* importing `app`.
_TMP = Path(tempfile.mkdtemp(prefix="agentic-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'urls.db').as_posix()}"
os.environ["WORKFLOW_DATABASE_URL"] = f"sqlite:///{(_TMP / 'workflows.db').as_posix()}"
os.environ["WORKSPACE_ROOT"] = (_TMP / "workspaces").as_posix()
os.environ["BASE_URL"] = "http://localhost:8000"

ROOT = Path(__file__).resolve().parents[1]

from tests.helpers import FakeRunner  # noqa: E402


@pytest.fixture
def make_engine(tmp_path):
    from orchestrator.engine import WorkflowEngine
    from orchestrator.store import WorkflowStore

    def factory(**overrides):
        options = {
            "store": WorkflowStore(f"sqlite:///{(tmp_path / 'wf.db').as_posix()}"),
            "workspace_root": tmp_path / "ws",
            "repo_root": ROOT,
            "test_runner": FakeRunner(),
            "max_retries": 2,
            "retry_backoff_ms": 5,
        }
        options.update(overrides)
        return WorkflowEngine(**options)

    return factory


@pytest.fixture
def engine(make_engine):
    return make_engine()


@pytest.fixture(autouse=True)
def reset_url_db():
    import app.models  # noqa: F401
    from app.core.database import Base
    from app.core.database import engine as db_engine

    Base.metadata.drop_all(bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    yield
    Base.metadata.drop_all(bind=db_engine)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api_client(engine):
    """TestClient whose workflow engine uses a temp store and a fast fake test runner."""
    from fastapi.testclient import TestClient

    from app.api.workflows import get_engine
    from app.main import app

    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
