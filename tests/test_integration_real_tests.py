"""Integration tests: the generated code is really tested by a pytest subprocess."""

import pytest

from orchestrator.models import ApprovalRequest, WorkflowRequest
from orchestrator.test_runner import PytestRunner
from tests.helpers import BROWNFIELD, GREENFIELD

pytestmark = pytest.mark.integration


def _approve(engine, state, gate):
    return engine.approve(
        state["id"], ApprovalRequest(gate=gate, approved=True, approver="Reviewer", comment="ok")
    )


def test_brownfield_expiration_is_generated_tested_and_released(make_engine):
    engine = make_engine(test_runner=PytestRunner(timeout_seconds=120))
    state = engine.start(WorkflowRequest(requirement=BROWNFIELD, scenario="brownfield"))
    state = _approve(engine, state, "implementation")

    assert state["status"] == "awaiting_release_approval"
    assert state["outputs"]["T5"]["passed"] >= 7  # a real pytest run, not a stub
    assert state["outputs"]["T5"]["failed"] == 0
    files = engine.artifacts(state["id"])["files"]
    assert {"src/expiration.py", "tests/test_expiration.py", "reports/test-report.txt"} <= set(
        files
    )

    state = _approve(engine, state, "release")
    assert state["status"] == "release_ready"
    assert "PASS: tests_passed" in engine.summary_document(state["id"])


def test_greenfield_generated_suite_passes_for_every_capability(make_engine):
    engine = make_engine(test_runner=PytestRunner(timeout_seconds=120))
    state = engine.start(WorkflowRequest(requirement=GREENFIELD, scenario="greenfield"))
    state = _approve(engine, state, "implementation")
    assert state["outputs"]["T5"]["passed"] == 7  # 4 shortcode + 3 analytics tests
    assert state["status"] == "awaiting_release_approval"


def test_a_genuinely_failing_test_triggers_retry_rollback_and_safe_stop(make_engine):
    engine = make_engine(test_runner=PytestRunner(timeout_seconds=120), max_retries=1)
    original = engine.handlers["T4"]

    def defective(ctx):
        output = original(ctx)
        path = ctx.workspace.write(
            "tests/test_regression.py", "def test_bug():\n    assert 1 == 2\n"
        )
        output["files"].append(path)
        output["artifacts"].append(path)
        return output

    engine.handlers["T4"] = defective
    state = engine.start(WorkflowRequest(requirement=BROWNFIELD, scenario="brownfield"))
    state = _approve(engine, state, "implementation")

    assert state["status"] == "safe_stopped_rolled_back"
    assert state["counters"]["retries"] == 1
    assert "did not pass" in state["incidents"][0]["error"]
    files = engine.artifacts(state["id"])["files"]
    assert not any(f.startswith(("src/", "tests/", "reports/")) for f in files)
