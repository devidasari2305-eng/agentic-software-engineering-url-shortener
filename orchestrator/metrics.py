"""Reliability metrics aggregated from persisted workflow state."""

from datetime import datetime

TERMINAL_STATUSES = frozenset(
    {
        "release_ready",
        "rejected_implementation",
        "rejected_release",
        "safe_stopped_policy",
        "safe_stopped_failure",
        "safe_stopped_rolled_back",
        "safe_stopped_validation",
    }
)


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def compute_metrics(states: list[dict]) -> dict:
    total = len(states)
    terminal = [s for s in states if s.get("status") in TERMINAL_STATUSES]
    succeeded = [s for s in terminal if s["status"] == "release_ready"]
    safe_stopped = [s for s in terminal if s["status"].startswith("safe_stopped")]
    rejected = [s for s in terminal if s["status"].startswith("rejected")]

    def counter(name: str) -> int:
        return sum(s.get("counters", {}).get(name, 0) for s in states)

    incidents = [i for s in states for i in s.get("incidents", [])]
    resolved = [i for i in incidents if i.get("mttr_ms") is not None]
    by_outcome: dict[str, list[float]] = {}
    for incident in resolved:
        by_outcome.setdefault(incident["kind"], []).append(incident["mttr_ms"])

    latencies = [s["end_to_end_latency_ms"] for s in terminal if s.get("end_to_end_latency_ms")]

    return {
        "total_workflows": total,
        "in_progress": total - len(terminal),
        "terminal_workflows": len(terminal),
        "succeeded": len(succeeded),
        "safe_stopped": len(safe_stopped),
        "rejected_by_human": len(rejected),
        "success_rate_pct": round(len(succeeded) / len(terminal) * 100, 2) if terminal else 0.0,
        "node_executions": counter("node_executions"),
        "failed_attempts": counter("failures"),
        "retries": counter("retries"),
        "retry_rate_per_workflow": round(counter("retries") / total, 2) if total else 0.0,
        "fallbacks": counter("fallbacks"),
        "rollbacks": counter("rollbacks"),
        "rollback_rate_pct": round(counter("rollbacks") / total * 100, 2) if total else 0.0,
        "replans": counter("replans"),
        "incidents": len(incidents),
        "resolved_incidents": len(resolved),
        "mttr_ms": _avg([i["mttr_ms"] for i in resolved]),
        "mttr_ms_by_outcome": {k: _avg(v) for k, v in sorted(by_outcome.items())},
        "avg_end_to_end_latency_ms": _avg(latencies),
        "avg_agent_execution_ms": _avg([s.get("execution_time_ms", 0.0) for s in states]),
        "definitions": {
            "success_rate": "release_ready / workflows in a terminal state",
            "mttr": "mean time from the first failed attempt to recovery (retry success, "
            "fallback success, or completed rollback to the last checkpoint)",
            "end_to_end_latency": "creation to terminal state, including human approval wait",
            "agent_execution": "wall-clock time spent executing agent batches only",
        },
    }


def parse_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None
