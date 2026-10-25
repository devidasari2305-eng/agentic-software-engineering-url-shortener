import threading

import pytest

from orchestrator.errors import ApprovalError, InvalidRequest, InvalidTransition, WorkflowNotFound
from orchestrator.models import ApprovalRequest, WorkflowRequest
from tests.helpers import AMBIGUOUS, BROWNFIELD, CLARIFIED, GREENFIELD, FakeRunner


def request(text, scenario="greenfield", **extra):
    return WorkflowRequest(requirement=text, scenario=scenario, **extra)


def approve(engine, state, gate="implementation", approved=True, comment="", who="Reviewer"):
    return engine.approve(
        state["id"],
        ApprovalRequest(gate=gate, approved=approved, approver=who, comment=comment),
    )


def finish(engine, state):
    state = approve(engine, state)
    return approve(engine, state, gate="release")


# ---------------------------------------------------------------- happy path and gates


def test_greenfield_runs_through_both_human_gates(engine):
    state = engine.start(request(GREENFIELD))
    assert state["status"] == "awaiting_implementation_approval"
    assert state["nodes"]["T4"]["status"] == "pending"  # nothing is implemented before approval

    state = approve(engine, state)
    assert state["status"] == "awaiting_release_approval"
    assert state["checkpoint"]["label"] == "v1-pre-implementation"

    state = approve(engine, state, gate="release")
    assert state["status"] == "release_ready"
    assert all(n["status"] == "completed" for n in state["nodes"].values())
    assert state["end_to_end_latency_ms"] > 0

    files = engine.artifacts(state["id"])["files"]
    assert {"src/shortcode.py", "src/click_counter.py", "docs/change-notes.md"} <= set(files)
    assert "Final engineering summary" in engine.summary_document(state["id"])


def test_release_gate_cannot_be_used_before_implementation_gate(engine):
    state = engine.start(request(GREENFIELD))
    with pytest.raises(InvalidTransition):
        approve(engine, state, gate="release")


def test_approvals_must_come_from_a_named_human(engine):
    state = engine.start(request(GREENFIELD))
    with pytest.raises(ApprovalError):
        approve(engine, state, who="agent")


def test_high_impact_change_requires_a_risk_acknowledgement_comment(engine):
    text = "Add a database migration to introduce a new column for URL expiration"
    state = engine.start(request(text, "brownfield"))
    assert state["gates"]["G1"]["review"]["requires_comment"] is True
    with pytest.raises(ApprovalError):
        approve(engine, state, comment="")
    state = approve(engine, state, comment="Reviewed rollback plan and migration impact")
    assert state["status"] == "awaiting_release_approval"


def test_rejection_is_terminal_until_a_human_replans(engine):
    state = engine.start(request(GREENFIELD))
    state = approve(engine, state, approved=False, comment="Scope too broad")
    assert state["status"] == "rejected_implementation"
    assert state["counters"]["rejections"] == 1
    assert state["nodes"]["T4"]["status"] == "pending"

    state = engine.replan(
        state["id"], "T1", "Narrowed scope", "Build a URL shortener API with click analytics only"
    )
    assert state["status"] == "awaiting_implementation_approval"
    assert state["version"] == 2


def test_unknown_workflow_raises(engine):
    with pytest.raises(WorkflowNotFound):
        engine.get("does-not-exist")


# ---------------------------------------------------------------- parallelism


def _barrier_wrapped(engine, node_ids):
    barrier = threading.Barrier(len(node_ids), timeout=5)
    for node_id in node_ids:
        original = engine.handlers[node_id]

        def wrapped(ctx, original=original):
            barrier.wait()  # only passes if every sibling node is running at the same time
            return original(ctx)

        engine.handlers[node_id] = wrapped


def test_architecture_and_security_run_concurrently(engine):
    _barrier_wrapped(engine, ["T2", "T3"])
    state = engine.start(request(BROWNFIELD, "brownfield"))
    assert state["status"] == "awaiting_implementation_approval"
    assert state["nodes"]["T2"]["parallel_group"] == state["nodes"]["T3"]["parallel_group"]
    assert state["counters"]["retries"] == 0


def test_tests_and_documentation_run_concurrently(engine):
    _barrier_wrapped(engine, ["T5", "T6"])
    state = approve(engine, engine.start(request(GREENFIELD)))
    assert state["status"] == "awaiting_release_approval"
    assert state["nodes"]["T5"]["parallel_group"] == state["nodes"]["T6"]["parallel_group"]
    assert state["counters"]["retries"] == 0


def test_synchronisation_waits_for_every_dependency(engine):
    state = engine.start(request(GREENFIELD))
    # G1 opened only after BOTH T2 and T3 completed; T7 only after BOTH T5 and T6.
    assert state["nodes"]["T2"]["status"] == state["nodes"]["T3"]["status"] == "completed"
    state = approve(engine, state)
    events = [e["event"] for e in engine.audit(state["id"])["events"]]
    assert events.index("gate_opened") < events.index("checkpoint_created")


# ---------------------------------------------------------------- ambiguity / clarification


def test_ambiguous_requirement_safe_stops_and_cannot_be_approved(engine):
    state = engine.start(request(AMBIGUOUS, "ambiguous"))
    assert state["status"] == "awaiting_clarification"
    assert state["nodes"]["T1"]["status"] == "blocked"
    assert state["nodes"]["T2"]["status"] == "pending"  # nothing downstream ran
    assert len(state["outputs"]["T1"]["ambiguities"]) >= 2
    with pytest.raises(InvalidTransition):
        approve(engine, state)


def test_clarification_unblocks_through_a_versioned_replan(engine):
    state = engine.start(request(AMBIGUOUS, "ambiguous"))
    with pytest.raises(InvalidRequest):
        engine.clarify(state["id"], AMBIGUOUS, "Product Owner")

    state = engine.clarify(state["id"], CLARIFIED, "Product Owner")
    assert state["status"] == "awaiting_implementation_approval"
    assert state["version"] == 2
    assert "caching" in state["outputs"]["T1"]["capabilities"]
    replan = next(d for d in state["decisions"] if d["type"] == "dynamic_replan")
    assert replan["kind"] == "clarification"

    state = finish(engine, state)
    assert state["status"] == "release_ready"
    assert "src/redirect_cache.py" in engine.artifacts(state["id"])["files"]


def test_clarify_is_rejected_when_nothing_to_clarify(engine):
    state = engine.start(request(GREENFIELD))
    with pytest.raises(InvalidTransition):
        engine.clarify(state["id"], CLARIFIED, "Product Owner")


# ---------------------------------------------------------------- policy


def test_policy_violation_safe_stops_without_retries(engine):
    state = engine.start(
        request("Deploy the new redirect cache directly to production", "brownfield")
    )
    assert state["status"] == "safe_stopped_policy"
    assert state["nodes"]["T3"]["attempts"] == 1  # non-retryable: never retried
    assert state["counters"]["retries"] == 0
    assert state["nodes"]["T4"]["status"] == "pending"
    assert "POL-001" in state["nodes"]["T3"]["error"]


# ---------------------------------------------------------------- retry / fallback / rollback


def test_transient_failure_is_retried_and_recovers(engine):
    state = engine.start(request(GREENFIELD, fault_injection={"T5": 1}))
    state = approve(engine, state)
    assert state["status"] == "awaiting_release_approval"
    assert state["nodes"]["T5"]["attempts"] == 2
    assert state["counters"]["retries"] == 1
    assert state["counters"]["rollbacks"] == 0
    incident = state["incidents"][0]
    assert incident["kind"] == "recovered"
    assert incident["mttr_ms"] >= 5  # includes the retry backoff


def test_exhausted_retries_roll_back_to_checkpoint_and_safe_stop(engine):
    state = engine.start(request(GREENFIELD, fault_injection={"T5": 99}))
    state = approve(engine, state)
    assert state["status"] == "safe_stopped_rolled_back"
    assert state["counters"]["retries"] == 2  # bounded: 1 attempt + 2 retries
    assert state["counters"]["rollbacks"] == 1
    assert all(state["nodes"][n]["status"] == "pending" for n in ("T4", "T5", "T6", "T7", "G2"))
    assert state["outputs"].keys() == {"T1", "T2", "T3"}

    files = engine.artifacts(state["id"])["files"]
    assert not any(f.startswith(("src/", "tests/", "docs/")) for f in files)  # really restored
    assert "analysis/requirements.json" in files
    assert state["incidents"][0]["kind"] == "rolled_back"
    assert state["incidents"][0]["mttr_ms"] is not None
    assert any(h["reason"] == "rollback" for h in state["history"])


def test_human_can_recover_from_rollback_by_replanning_from_the_failed_stage(engine):
    state = engine.start(request(GREENFIELD, fault_injection={"T5": 3}))  # exactly exhausts retries
    state = approve(engine, state)
    assert state["status"] == "safe_stopped_rolled_back"

    state = engine.replan(state["id"], "T4", "Test infrastructure fixed")
    assert state["status"] == "awaiting_release_approval"
    assert state["decisions"][-1]["preserved"] == ["G1", "T1", "T2", "T3"]  # G1 approval kept
    assert state["counters"]["rollbacks"] == 1 and state["counters"]["replans"] == 1


def test_ai_provider_failure_falls_back_to_deterministic_provider(engine):
    state = engine.start(request(GREENFIELD, fault_injection={"T1": 99}))
    assert state["status"] == "awaiting_implementation_approval"
    assert state["nodes"]["T1"]["via"] == "fallback"
    assert state["outputs"]["T1"]["provider"] == "deterministic (fallback)"
    assert state["counters"]["fallbacks"] == 1
    assert state["incidents"][0]["kind"] == "fallback"


def test_failure_before_the_checkpoint_safe_stops_without_rollback(engine):
    engine.handlers["T2"] = lambda ctx: (_ for _ in ()).throw(RuntimeError("scanner crashed"))
    state = engine.start(request(BROWNFIELD, "brownfield"))
    assert state["status"] == "safe_stopped_failure"
    assert state["counters"]["rollbacks"] == 0
    assert state["counters"]["retries"] == 2
    assert state["incidents"][0]["kind"] == "failed"


def test_failing_release_validation_is_not_retried(engine):
    engine.test_runner = FakeRunner(passed=0)  # zero tests executed -> T5 would fail; bypass it
    engine.handlers["T5"] = lambda ctx: {"passed": 0, "failed": 0, "artifacts": []}
    state = approve(engine, engine.start(request(GREENFIELD)))
    assert state["status"] == "safe_stopped_validation"
    assert state["nodes"]["T7"]["attempts"] == 1
    assert "tests_passed" in state["nodes"]["T7"]["error"]


def test_fault_injection_is_validated(engine, make_engine):
    with pytest.raises(InvalidRequest):
        engine.start(request(GREENFIELD, fault_injection={"G1": 1}))
    with pytest.raises(InvalidRequest):
        engine.start(request(GREENFIELD, fault_injection={"T5": 0}))
    with pytest.raises(InvalidRequest):
        make_engine(allow_fault_injection=False).start(
            request(GREENFIELD, fault_injection={"T5": 1})
        )


# ---------------------------------------------------------------- dynamic re-planning


def test_upstream_output_change_replans_only_the_affected_branch(engine):
    state = engine.start(request(BROWNFIELD, "brownfield"))
    original_t3 = state["outputs"]["T3"]

    state = engine.replan(state["id"], "T2", "Impact analysis flagged as stale")
    decision = state["decisions"][-1]
    assert decision["type"] == "dynamic_replan"
    assert decision["preserved"] == ["T1", "T3"]
    assert decision["invalidated"] == ["G1", "G2", "T2", "T4", "T5", "T6", "T7"]
    assert state["outputs"]["T3"] == original_t3  # unaffected work is reused, not recomputed
    assert state["nodes"]["T3"]["attempts"] == 1
    assert state["version"] == 2 and state["counters"]["replans"] == 1
    assert state["status"] == "awaiting_implementation_approval"
    assert any(h["node_id"] == "T2" for h in state["history"])  # decision lineage kept


def test_requirement_change_invalidates_everything_downstream(engine):
    state = engine.start(request(BROWNFIELD, "brownfield"))
    new = "Add expiration only for newly created URLs; existing URLs never expire"
    state = engine.replan(state["id"], "T1", "Product owner changed scope", new)
    assert state["requirement"] == new
    assert state["original_requirement"] == BROWNFIELD
    assert state["outputs"]["T1"]["normalized_problem"] == new
    change = state["decisions"][-1]["requirement_change"]
    assert change == {"from": BROWNFIELD, "to": new}
    assert state["decisions"][-1]["preserved"] == []


def test_replan_after_implementation_removes_stale_artifacts_and_reopens_the_gate(engine):
    state = approve(engine, engine.start(request(GREENFIELD)))
    assert "src/shortcode.py" in engine.artifacts(state["id"])["files"]

    state = engine.replan(state["id"], "T2", "Architecture decision reversed")
    assert state["status"] == "awaiting_implementation_approval"  # human must re-approve
    assert state["checkpoint"] is None
    files = engine.artifacts(state["id"])["files"]
    assert not any(f.startswith(("src/", "tests/", "docs/", "release/")) for f in files)
    assert "analysis/requirements.json" in files  # preserved branch kept its artifact


def test_released_workflows_are_immutable_and_replans_are_validated(engine):
    state = finish(engine, engine.start(request(GREENFIELD)))
    assert state["status"] == "release_ready"
    with pytest.raises(InvalidTransition):
        engine.replan(state["id"], "T2", "Too late")

    fresh = engine.start(request(GREENFIELD))
    with pytest.raises(InvalidRequest):
        engine.replan(fresh["id"], "G1", "Gates cannot be a replan root")
    with pytest.raises(InvalidRequest):
        engine.replan(fresh["id"], "T9", "No such node")
    with pytest.raises(InvalidRequest):
        engine.replan(fresh["id"], "T2", "Requirement edits start at T1", "Some other requirement")


# ---------------------------------------------------------------- durability, audit, metrics


def test_workflow_survives_an_engine_restart(make_engine):
    first = make_engine()
    state = first.start(request(GREENFIELD))
    second = make_engine()  # new process: same database and workspace, no in-memory state
    state = approve(second, state)
    assert state["status"] == "awaiting_release_approval"
    assert approve(second, state, gate="release")["status"] == "release_ready"


def test_audit_log_is_complete_and_tamper_evident(engine):
    state = finish(engine, engine.start(request(GREENFIELD)))
    audit = engine.audit(state["id"])
    assert audit["integrity"]["valid"] is True
    events = [e["event"] for e in audit["events"]]
    for expected in (
        "workflow_created",
        "batch_started",
        "node_completed",
        "gate_opened",
        "approval_recorded",
        "checkpoint_created",
        "workflow_completed",
    ):
        assert expected in events
    assert [e["seq"] for e in audit["events"]] == list(range(1, len(events) + 1))


def test_reliability_metrics_aggregate_across_workflows(engine):
    finish(engine, engine.start(request(GREENFIELD)))
    finish(engine, engine.start(request(GREENFIELD, fault_injection={"T5": 1})))
    approve(engine, engine.start(request(GREENFIELD, fault_injection={"T5": 99})))

    metrics = engine.metrics()
    assert metrics["total_workflows"] == 3
    assert metrics["terminal_workflows"] == 3
    assert metrics["succeeded"] == 2 and metrics["safe_stopped"] == 1
    assert metrics["success_rate_pct"] == 66.67
    assert metrics["retries"] == 3  # 1 transient + 2 before rollback
    assert metrics["rollbacks"] == 1
    assert metrics["incidents"] == 2
    assert set(metrics["mttr_ms_by_outcome"]) == {"recovered", "rolled_back"}
    assert metrics["mttr_ms"] > 0
    assert metrics["avg_end_to_end_latency_ms"] > 0
