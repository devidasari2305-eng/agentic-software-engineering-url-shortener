from orchestrator.metrics import compute_metrics


def _state(status, retries=0, rollbacks=0, incidents=(), latency=100.0):
    return {
        "status": status,
        "counters": {"retries": retries, "rollbacks": rollbacks, "node_executions": 7},
        "incidents": list(incidents),
        "end_to_end_latency_ms": latency,
        "execution_time_ms": 40.0,
    }


def test_empty_metrics_are_zero_not_errors():
    metrics = compute_metrics([])
    assert metrics["total_workflows"] == 0
    assert metrics["success_rate_pct"] == 0.0
    assert metrics["mttr_ms"] == 0.0


def test_success_rate_counts_only_terminal_workflows():
    metrics = compute_metrics(
        [
            _state("release_ready"),
            _state("safe_stopped_rolled_back", retries=2, rollbacks=1),
            _state("awaiting_implementation_approval"),
        ]
    )
    assert metrics["total_workflows"] == 3
    assert metrics["in_progress"] == 1
    assert metrics["terminal_workflows"] == 2
    assert metrics["success_rate_pct"] == 50.0
    assert metrics["retries"] == 2 and metrics["rollbacks"] == 1


def test_mttr_averages_resolved_incidents_by_outcome():
    incidents = [
        {"node": "T5", "kind": "recovered", "mttr_ms": 10.0},
        {"node": "T5", "kind": "recovered", "mttr_ms": 30.0},
        {"node": "T5", "kind": "rolled_back", "mttr_ms": 100.0},
        {"node": "T2", "kind": "failed", "mttr_ms": None},
    ]
    metrics = compute_metrics([_state("release_ready", incidents=incidents)])
    assert metrics["incidents"] == 4 and metrics["resolved_incidents"] == 3
    assert metrics["mttr_ms"] == 46.67
    assert metrics["mttr_ms_by_outcome"] == {"recovered": 20.0, "rolled_back": 100.0}
