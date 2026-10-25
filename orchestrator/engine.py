"""Stateful, governed workflow engine.

The engine executes the dependency graph: it finds *ready* nodes, runs independent ones in
parallel, synchronises on their dependencies, pauses at human gates, applies bounded retries,
fallback and checkpoint rollback, dynamically re-plans when upstream outputs change, and
records every step in a hash-chained audit log. All state is persisted after each transition,
so a restarted process can resume any workflow.
"""

import copy
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from orchestrator.agents import (
    architecture,
    documentation,
    implementation,
    release,
    requirement,
    security,
    testing,
)
from orchestrator.agents.base import NodeContext
from orchestrator.codebase import CodebaseAnalyzer
from orchestrator.errors import (
    ApprovalError,
    InjectedFault,
    InvalidRequest,
    InvalidTransition,
    NonRetryableError,
    WorkflowNotFound,
)
from orchestrator.graph import DependencyGraph
from orchestrator.metrics import TERMINAL_STATUSES, compute_metrics, parse_iso
from orchestrator.models import ApprovalRequest, WorkflowRequest
from orchestrator.policy import PolicyEngine
from orchestrator.providers.base import AIProvider
from orchestrator.providers.deterministic import DeterministicProvider
from orchestrator.store import WorkflowStore
from orchestrator.test_runner import PytestRunner
from orchestrator.workspace import Workspace

GATE_FOR = {"implementation": "G1", "release": "G2"}
AWAITING_STATUS = {"G1": "awaiting_implementation_approval", "G2": "awaiting_release_approval"}
REJECTED_STATUS = {"G1": "rejected_implementation", "G2": "rejected_release"}
ROLLBACK_NODES = frozenset({"T4", "T5", "T6"})
NON_HUMAN_APPROVERS = {"agent", "system", "ai", "bot", "copilot", "assistant"}

Handler = Callable[[NodeContext], dict]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class NodeResult:
    ok: bool
    output: dict | None = None
    attempts: list[dict] = field(default_factory=list)
    via: str = "primary"
    duration_ms: float = 0.0
    recovery_ms: float | None = None
    error: str | None = None
    error_type: str | None = None


class FaultInjector:
    """Thread-safe, deterministic failure injection for demonstrating recovery behaviour."""

    def __init__(self, remaining: dict[str, int]):
        self._remaining = dict(remaining)
        self._lock = threading.Lock()

    def maybe_fail(self, node_id: str) -> None:
        with self._lock:
            if self._remaining.get(node_id, 0) > 0:
                self._remaining[node_id] -= 1
                raise InjectedFault(f"Injected fault in {node_id}")

    def remaining(self) -> dict[str, int]:
        with self._lock:
            return {k: v for k, v in self._remaining.items() if v > 0}


class WorkflowEngine:
    def __init__(
        self,
        store: WorkflowStore,
        workspace_root: Path,
        repo_root: Path,
        provider: AIProvider | None = None,
        fallback_provider: AIProvider | None = None,
        test_runner=None,
        policy: PolicyEngine | None = None,
        max_retries: int = 2,
        retry_backoff_ms: int = 0,
        max_parallel_tasks: int = 4,
        allow_fault_injection: bool = True,
    ):
        self.store = store
        self.workspace_root = Path(workspace_root)
        self.provider = provider or DeterministicProvider()
        self.fallback_provider = fallback_provider or DeterministicProvider()
        self.test_runner = test_runner or PytestRunner()
        self.policy = policy or PolicyEngine()
        self.analyzer = CodebaseAnalyzer(Path(repo_root))
        self.graph = DependencyGraph()
        self.max_retries = max_retries
        self.retry_backoff_ms = retry_backoff_ms
        self.max_parallel_tasks = max_parallel_tasks
        self.allow_fault_injection = allow_fault_injection

        self.handlers: dict[str, Handler] = {
            "T1": requirement.run,
            "T2": architecture.run,
            "T3": security.run,
            "T4": implementation.run,
            "T5": testing.run,
            "T6": documentation.run,
            "T7": release.run,
        }
        self.fallbacks: dict[str, Handler] = {"T1": requirement.run_fallback}

        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    # ------------------------------------------------------------------ public API

    def start(self, request: WorkflowRequest) -> dict:
        faults = self._validated_faults(request.fault_injection)
        state = self._new_state(request, faults)
        with self._lock(state["id"]):
            self._persist(state)
            self._audit(
                state,
                None,
                "workflow_created",
                {"scenario": request.scenario, "requested_by": request.requested_by},
            )
            self._advance(state)
            return self._view(state)

    def get(self, workflow_id: str) -> dict:
        return self._view(self._load(workflow_id))

    def list_workflows(self) -> list[dict]:
        return [
            {
                "id": s["id"],
                "requirement": s["requirement"],
                "scenario": s["scenario"],
                "status": s["status"],
                "version": s["version"],
                "created_at": s["created_at"],
            }
            for s in self.store.all_states()
        ]

    def approve(self, workflow_id: str, request: ApprovalRequest) -> dict:
        with self._lock(workflow_id):
            state = self._load(workflow_id)
            gate_id = GATE_FOR[request.gate]
            node = state["nodes"][gate_id]
            if node["status"] != "awaiting_approval":
                raise InvalidTransition(
                    f"The {request.gate} gate is not awaiting approval "
                    f"(workflow status: {state['status']})"
                )
            if request.approver.strip().lower() in NON_HUMAN_APPROVERS:
                raise ApprovalError("Approvals must be given by a named human reviewer")
            review = state["gates"][gate_id]["review"]
            if request.approved and review.get("requires_comment") and not request.comment.strip():
                raise ApprovalError(
                    "This is a high-impact change: an approval comment acknowledging the risk "
                    "is mandatory"
                )

            decision = {
                "gate": gate_id,
                "approved": request.approved,
                "approver": request.approver,
                "comment": request.comment,
                "decided_at": now_iso(),
                "workflow_version": state["version"],
            }
            state["gates"][gate_id]["decision"] = decision
            state["decisions"].append({"type": "approval", **decision})
            self._audit(state, gate_id, "approval_recorded", decision)

            if not request.approved:
                node["status"] = "rejected"
                state["counters"]["rejections"] += 1
                self._set_status(state, REJECTED_STATUS[gate_id])
                self._persist(state)
                return self._view(state)

            node["status"] = "completed"
            node["finished_at"] = now_iso()
            state["counters"]["approvals"] += 1
            if gate_id == "G1":
                checkpoint = self._workspace(state["id"]).snapshot(
                    f"v{state['version']}-pre-implementation"
                )
                checkpoint["created_at"] = now_iso()
                checkpoint["version"] = state["version"]
                state["checkpoint"] = checkpoint
                self._audit(state, gate_id, "checkpoint_created", checkpoint)
            self._advance(state)
            return self._view(state)

    def clarify(self, workflow_id: str, clarified_requirement: str, author: str) -> dict:
        with self._lock(workflow_id):
            state = self._load(workflow_id)
            if state["status"] != "awaiting_clarification":
                raise InvalidTransition(
                    f"Workflow is not awaiting clarification (status: {state['status']})"
                )
            if clarified_requirement.strip() == state["requirement"].strip():
                raise InvalidRequest("The clarified requirement must differ from the original")
            return self._replan(
                state,
                "T1",
                f"Clarification supplied by {author}",
                clarified_requirement,
                author,
                kind="clarification",
            )

    def replan(
        self,
        workflow_id: str,
        changed_node: str,
        reason: str,
        new_requirement: str | None = None,
        requested_by: str = "anonymous",
    ) -> dict:
        with self._lock(workflow_id):
            state = self._load(workflow_id)
            return self._replan(state, changed_node, reason, new_requirement, requested_by)

    def audit(self, workflow_id: str) -> dict:
        self._load(workflow_id)
        return {
            "workflow_id": workflow_id,
            "integrity": self.store.verify_chain(workflow_id),
            "events": self.store.audit(workflow_id),
        }

    def metrics(self) -> dict:
        return compute_metrics(self.store.all_states())

    def graph_view(self, workflow_id: str) -> dict:
        state = self._load(workflow_id)
        statuses = {nid: n["status"] for nid, n in state["nodes"].items()}
        return {
            "layers": self.graph.layers(),
            "nodes": list(state["nodes"].values()),
            "mermaid": self.graph.to_mermaid(statuses),
        }

    def artifacts(self, workflow_id: str) -> dict:
        state = self._load(workflow_id)
        return {"workflow_id": workflow_id, "files": self._workspace(state["id"]).manifest()}

    def summary_document(self, workflow_id: str) -> str:
        state = self._load(workflow_id)
        workspace = self._workspace(state["id"])
        if not workspace.exists("release/engineering-summary.md"):
            raise InvalidTransition("The engineering summary has not been generated yet")
        return workspace.read("release/engineering-summary.md")

    # ------------------------------------------------------------------ state helpers

    def _lock(self, workflow_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(workflow_id, threading.RLock())

    def _load(self, workflow_id: str) -> dict:
        state = self.store.load(workflow_id)
        if state is None:
            raise WorkflowNotFound(f"Workflow not found: {workflow_id}")
        return state

    def _workspace(self, workflow_id: str) -> Workspace:
        return Workspace(self.workspace_root / workflow_id)

    def _persist(self, state: dict) -> None:
        state["updated_at"] = now_iso()
        self.store.save(state)

    def _audit(self, state: dict, node_id: str | None, event: str, detail: dict) -> None:
        self.store.append_audit(state["id"], node_id, event, detail)

    def _set_status(self, state: dict, status: str) -> None:
        previous = state["status"]
        if previous == status:
            return
        state["status"] = status
        if status in TERMINAL_STATUSES:
            state["completed_at"] = now_iso()
            created, finished = parse_iso(state["created_at"]), parse_iso(state["completed_at"])
            state["end_to_end_latency_ms"] = round((finished - created).total_seconds() * 1000, 2)
        else:
            state["completed_at"] = None
            state["end_to_end_latency_ms"] = None
        self._audit(state, None, "status_changed", {"from": previous, "to": status})

    def _validated_faults(self, faults: dict[str, int] | None) -> dict[str, int]:
        if not faults:
            return {}
        if not self.allow_fault_injection:
            raise InvalidRequest("Fault injection is disabled in this environment")
        for node_id, count in faults.items():
            if not self.graph.has(node_id) or self.graph.spec(node_id).kind != "task":
                raise InvalidRequest(f"Fault injection target must be a task node, got {node_id}")
            if not 1 <= count <= 99:
                raise InvalidRequest("Fault injection count must be between 1 and 99")
        return dict(faults)

    def _new_state(self, request: WorkflowRequest, faults: dict[str, int]) -> dict:
        created = now_iso()
        return {
            "id": str(uuid.uuid4()),
            "requirement": request.requirement.strip(),
            "original_requirement": request.requirement.strip(),
            "scenario": request.scenario,
            "requested_by": request.requested_by,
            "status": "running",
            "version": 1,
            "created_at": created,
            "updated_at": created,
            "completed_at": None,
            "end_to_end_latency_ms": None,
            "execution_time_ms": 0.0,
            "nodes": {
                s.id: {
                    "id": s.id,
                    "name": s.name,
                    "kind": s.kind,
                    "depends_on": list(s.depends_on),
                    "status": "pending",
                    "attempts": 0,
                    "started_at": None,
                    "finished_at": None,
                    "duration_ms": None,
                    "error": None,
                    "via": None,
                    "parallel_group": None,
                }
                for s in self.graph.specs
            },
            "outputs": {},
            "history": [],
            "decisions": [],
            "incidents": [],
            "gates": {},
            "checkpoint": None,
            "faults": faults,
            "counters": {
                "node_executions": 0,
                "retries": 0,
                "failures": 0,
                "fallbacks": 0,
                "rollbacks": 0,
                "replans": 0,
                "approvals": 0,
                "rejections": 0,
                "parallel_batches": 0,
            },
        }

    def _view(self, state: dict) -> dict:
        view = copy.deepcopy(state)
        view["parallel_layers"] = self.graph.layers()
        return view

    # ------------------------------------------------------------------ execution loop

    def _advance(self, state: dict) -> None:
        self._set_status(state, "running")
        while True:
            statuses = {nid: n["status"] for nid, n in state["nodes"].items()}
            ready = self.graph.ready(statuses)
            tasks = [spec for spec in ready if spec.kind == "task"]
            gates = [spec for spec in ready if spec.kind == "gate"]

            if tasks:
                if self._run_batch(state, tasks):
                    break
                if self._check_ambiguity(state):
                    break
                self._persist(state)
                continue
            if gates:
                self._open_gate(state, gates[0].id)
                break
            if all(n["status"] == "completed" for n in state["nodes"].values()):
                self._set_status(state, "release_ready")
                self._audit(state, None, "workflow_completed", {"version": state["version"]})
                break
            if not any(
                n["status"] in {"awaiting_approval", "blocked"} for n in state["nodes"].values()
            ):
                self._set_status(state, "safe_stopped_failure")
                self._audit(state, None, "deadlock_detected", {"statuses": statuses})
            break
        self._persist(state)

    def _run_batch(self, state: dict, specs: list) -> bool:
        """Run ready nodes concurrently. Returns True if the workflow was safe-stopped."""
        state["counters"]["parallel_batches"] += 1
        group = f"B{state['counters']['parallel_batches']}"
        started_iso = now_iso()
        self._audit(
            state,
            None,
            "batch_started",
            {"group": group, "nodes": [s.id for s in specs], "parallel": len(specs) > 1},
        )
        for spec in specs:
            node = state["nodes"][spec.id]
            node.update(status="running", started_at=started_iso, parallel_group=group, error=None)
            self._audit(state, spec.id, "node_started", {"group": group})

        injector = FaultInjector(state["faults"])
        context = self._context(state)
        batch_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(len(specs), self.max_parallel_tasks)) as pool:
            futures = [
                (spec, pool.submit(self._run_node, spec, context, injector)) for spec in specs
            ]
            results = [(spec, future.result()) for spec, future in futures]
        state["execution_time_ms"] = round(
            state["execution_time_ms"] + (time.perf_counter() - batch_started) * 1000, 2
        )
        state["faults"] = injector.remaining()

        failures = []
        for spec, result in results:
            self._record_result(state, spec.id, result)
            if not result.ok:
                failures.append((spec, result))
        if failures:
            self._handle_failure(state, failures)
            return True
        return False

    def _context(self, state: dict) -> NodeContext:
        return NodeContext(
            workflow_id=state["id"],
            requirement=state["requirement"],
            scenario=state["scenario"],
            version=state["version"],
            outputs=copy.deepcopy(state["outputs"]),
            workspace=self._workspace(state["id"]),
            provider=self.provider,
            fallback_provider=self.fallback_provider,
            policy=self.policy,
            analyzer=self.analyzer,
            test_runner=self.test_runner,
            checkpoint=copy.deepcopy(state["checkpoint"]),
            counters=dict(state["counters"]),
            incidents=copy.deepcopy(state["incidents"]),
            nodes={
                nid: {
                    "name": n["name"],
                    "status": n["status"],
                    "depends_on": n["depends_on"],
                    "attempts": n["attempts"],
                }
                for nid, n in state["nodes"].items()
            },
            decisions=copy.deepcopy(state["decisions"]),
        )

    def _run_node(self, spec, context: NodeContext, injector: FaultInjector) -> NodeResult:
        """Executed in a worker thread. Touches no shared state: it only returns a result."""
        handler = self.handlers[spec.id]
        max_attempts = 1 + (self.max_retries if spec.retryable else 0)
        attempts: list[dict] = []
        first_failure: float | None = None
        last_error: Exception | None = None
        started = time.perf_counter()

        for number in range(1, max_attempts + 1):
            attempt_started = time.perf_counter()
            try:
                injector.maybe_fail(spec.id)
                output = handler(context)
            except NonRetryableError as exc:
                first_failure = first_failure or attempt_started
                attempts.append(self._attempt(number, attempt_started, "primary", exc))
                last_error = exc
                break
            except Exception as exc:  # noqa: BLE001 - any agent failure is retried, then escalated
                first_failure = first_failure or attempt_started
                attempts.append(self._attempt(number, attempt_started, "primary", exc))
                last_error = exc
                if number < max_attempts and self.retry_backoff_ms:
                    time.sleep(self.retry_backoff_ms * (2 ** (number - 1)) / 1000)
                continue
            attempts.append(self._attempt(number, attempt_started, "primary", None))
            return NodeResult(
                ok=True,
                output=output,
                attempts=attempts,
                via="primary",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                recovery_ms=self._since(first_failure),
            )

        fallback = self.fallbacks.get(spec.id)
        if fallback is not None and not isinstance(last_error, NonRetryableError):
            attempt_started = time.perf_counter()
            try:
                output = fallback(context)
            except Exception as exc:  # noqa: BLE001
                attempts.append(self._attempt(len(attempts) + 1, attempt_started, "fallback", exc))
                last_error = exc
            else:
                attempts.append(self._attempt(len(attempts) + 1, attempt_started, "fallback", None))
                return NodeResult(
                    ok=True,
                    output=output,
                    attempts=attempts,
                    via="fallback",
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    recovery_ms=self._since(first_failure),
                )

        return NodeResult(
            ok=False,
            attempts=attempts,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            recovery_ms=self._since(first_failure),
            error=str(last_error),
            error_type=type(last_error).__name__,
        )

    @staticmethod
    def _attempt(number: int, started: float, via: str, error: Exception | None) -> dict:
        return {
            "attempt": number,
            "via": via,
            "ok": error is None,
            "error": None if error is None else str(error),
            "error_type": None if error is None else type(error).__name__,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    @staticmethod
    def _since(start: float | None) -> float | None:
        return None if start is None else round((time.perf_counter() - start) * 1000, 2)

    def _record_result(self, state: dict, node_id: str, result: NodeResult) -> None:
        node = state["nodes"][node_id]
        counters = state["counters"]
        primary = [a for a in result.attempts if a["via"] == "primary"]
        node["attempts"] += len(result.attempts)
        node["finished_at"] = now_iso()
        node["duration_ms"] = result.duration_ms
        counters["node_executions"] += len(result.attempts)
        counters["retries"] += max(0, len(primary) - 1)

        for attempt in result.attempts:
            if not attempt["ok"]:
                counters["failures"] += 1
                self._audit(state, node_id, "attempt_failed", attempt)

        if result.ok:
            node.update(status="completed", via=result.via, error=None)
            state["outputs"][node_id] = result.output
            if result.recovery_ms is not None:
                kind = "fallback" if result.via == "fallback" else "recovered"
                if kind == "fallback":
                    counters["fallbacks"] += 1
                    self._audit(
                        state, node_id, "fallback_used", {"provider": result.output.get("provider")}
                    )
                state["incidents"].append(
                    {
                        "node": node_id,
                        "kind": kind,
                        "attempts": len(result.attempts),
                        "opened_at": node["started_at"],
                        "resolved_at": now_iso(),
                        "mttr_ms": result.recovery_ms,
                    }
                )
            self._audit(
                state,
                node_id,
                "node_completed",
                {
                    "attempts": len(result.attempts),
                    "via": result.via,
                    "duration_ms": result.duration_ms,
                },
            )
        else:
            node.update(status="failed", error=result.error)
            self._audit(
                state,
                node_id,
                "node_failed",
                {
                    "error": result.error,
                    "error_type": result.error_type,
                    "attempts": len(result.attempts),
                },
            )

    def _handle_failure(self, state: dict, failures: list) -> None:
        failed_ids = [spec.id for spec, _ in failures]
        error_types = {result.error_type for _, result in failures}
        reason = "; ".join(f"{spec.id}: {result.error}" for spec, result in failures)
        needs_rollback = state["checkpoint"] is not None and any(
            node_id in ROLLBACK_NODES for node_id in failed_ids
        )
        rollback_ms = self._rollback(state, reason) if needs_rollback else 0.0

        for spec, result in failures:
            rolled_back = needs_rollback and spec.id in ROLLBACK_NODES
            state["incidents"].append(
                {
                    "node": spec.id,
                    "kind": "rolled_back" if rolled_back else "failed",
                    "attempts": len(result.attempts),
                    "opened_at": state["nodes"][spec.id]["started_at"],
                    "resolved_at": now_iso() if rolled_back else None,
                    "mttr_ms": round((result.recovery_ms or 0.0) + rollback_ms, 2)
                    if rolled_back
                    else None,
                    "error": result.error,
                }
            )

        if "PolicyViolation" in error_types:
            status = "safe_stopped_policy"
        elif "ValidationFailure" in error_types:
            status = "safe_stopped_validation"
        elif needs_rollback:
            status = "safe_stopped_rolled_back"
        else:
            status = "safe_stopped_failure"
        state["decisions"].append(
            {
                "type": "safe_stop",
                "status": status,
                "reason": reason,
                "rolled_back": needs_rollback,
                "decided_at": now_iso(),
            }
        )
        self._audit(state, None, "safe_stop", {"status": status, "reason": reason})
        self._set_status(state, status)

    def _rollback(self, state: dict, reason: str) -> float:
        started = time.perf_counter()
        checkpoint = state["checkpoint"]
        self._workspace(state["id"]).restore(checkpoint["label"])
        reset = []
        for node_id in sorted(self.graph.descendants("G1")):
            output = state["outputs"].pop(node_id, None)
            if output is not None:
                state["history"].append(
                    {
                        "node_id": node_id,
                        "version": state["version"],
                        "reason": "rollback",
                        "archived_at": now_iso(),
                        "output": output,
                    }
                )
            node = state["nodes"][node_id]
            node.update(
                status="pending",
                attempts=0,
                started_at=None,
                finished_at=None,
                duration_ms=None,
                via=None,
                parallel_group=None,
                error=None,
            )
            state["gates"].pop(node_id, None)
            reset.append(node_id)
        state["counters"]["rollbacks"] += 1
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        self._audit(
            state,
            None,
            "rollback_completed",
            {
                "restored_checkpoint": checkpoint["label"],
                "reset_nodes": reset,
                "reason": reason,
                "duration_ms": elapsed,
            },
        )
        return elapsed

    def _check_ambiguity(self, state: dict) -> bool:
        node = state["nodes"]["T1"]
        output = state["outputs"].get("T1")
        if node["status"] != "completed" or not output or not output.get("ambiguities"):
            return False
        node["status"] = "blocked"
        state["decisions"].append(
            {
                "type": "safe_stop",
                "reason": "material_ambiguity",
                "questions": output["ambiguities"],
                "decided_at": now_iso(),
            }
        )
        self._audit(state, "T1", "awaiting_clarification", {"questions": output["ambiguities"]})
        self._set_status(state, "awaiting_clarification")
        return True

    # ------------------------------------------------------------------ gates

    def _open_gate(self, state: dict, gate_id: str) -> None:
        state["nodes"][gate_id]["status"] = "awaiting_approval"
        state["nodes"][gate_id]["started_at"] = now_iso()
        review = self._gate_review(state, gate_id)
        state["gates"][gate_id] = {
            "status": "awaiting_approval",
            "opened_at": now_iso(),
            "review": review,
        }
        self._audit(state, gate_id, "gate_opened", {"requires_comment": review["requires_comment"]})
        self._set_status(state, AWAITING_STATUS[gate_id])

    def _gate_review(self, state: dict, gate_id: str) -> dict:
        outputs = state["outputs"]
        t1, t2, t3 = outputs.get("T1", {}), outputs.get("T2", {}), outputs.get("T3", {})
        approval_rules = t3.get("approval_required_rules", [])
        high_impact = t1.get("risk_level") == "high" or bool(approval_rules)
        if gate_id == "G1":
            impact = t2.get("impact") or {}
            return {
                "requirement": state["requirement"],
                "plan_version": state["version"],
                "risk_level": t1.get("risk_level"),
                "capabilities": t1.get("capabilities", []),
                "impacted_modules": [m["module"] for m in impact.get("direct_modules", [])],
                "dependent_modules": [m["module"] for m in impact.get("dependent_modules", [])],
                "proposed_components": t2.get("components", []),
                "policy_rules_requiring_approval": approval_rules,
                "rollback_plan": t2.get("rollback_strategy"),
                "requires_comment": high_impact,
                "recommendation": "approve with comment" if high_impact else "approve",
            }
        t5, t7 = outputs.get("T5", {}), outputs.get("T7", {})
        return {
            "readiness_checks": t7.get("checks", {}),
            "tests": {"passed": t5.get("passed"), "failed": t5.get("failed")},
            "summary_document": t7.get("summary_document"),
            "reliability": {
                k: state["counters"][k] for k in ("retries", "fallbacks", "rollbacks", "replans")
            },
            "requires_comment": high_impact,
            "recommendation": "approve" if t7.get("ready") else "reject",
        }

    # ------------------------------------------------------------------ dynamic re-planning

    def _replan(
        self,
        state: dict,
        changed_node: str,
        reason: str,
        new_requirement: str | None,
        requested_by: str,
        kind: str = "replan",
    ) -> dict:
        if not self.graph.has(changed_node) or self.graph.spec(changed_node).kind != "task":
            raise InvalidRequest(f"changed_node must be a task node, got {changed_node}")
        if state["status"] == "release_ready":
            raise InvalidTransition("A released workflow is immutable; start a new workflow")
        if new_requirement is not None and changed_node != "T1":
            raise InvalidRequest("A requirement change must re-plan from T1")

        invalidated = {changed_node} | self.graph.descendants(changed_node)
        preserved = sorted(
            nid
            for nid, n in state["nodes"].items()
            if n["status"] == "completed" and nid not in invalidated
        )
        previous_version = state["version"]
        previous_requirement = state["requirement"]

        workspace = self._workspace(state["id"])
        for node_id in sorted(invalidated):
            output = state["outputs"].pop(node_id, None)
            if output is not None:
                for artifact in output.get("artifacts", []):
                    workspace.delete(artifact)
                state["history"].append(
                    {
                        "node_id": node_id,
                        "version": previous_version,
                        "reason": reason,
                        "archived_at": now_iso(),
                        "output": output,
                    }
                )
            state["nodes"][node_id].update(
                status="pending",
                attempts=0,
                started_at=None,
                finished_at=None,
                duration_ms=None,
                error=None,
                via=None,
                parallel_group=None,
            )
            state["gates"].pop(node_id, None)
        if "G1" in invalidated:
            state["checkpoint"] = None

        state["version"] += 1
        if new_requirement is not None:
            state["requirement"] = new_requirement.strip()
        state["counters"]["replans"] += 1
        decision = {
            "type": "dynamic_replan",
            "kind": kind,
            "changed_node": changed_node,
            "reason": reason,
            "requested_by": requested_by,
            "from_version": previous_version,
            "to_version": state["version"],
            "invalidated": sorted(invalidated),
            "preserved": preserved,
            "requirement_change": (
                {"from": previous_requirement, "to": state["requirement"]}
                if new_requirement is not None
                else None
            ),
            "decided_at": now_iso(),
        }
        state["decisions"].append(decision)
        self._audit(state, changed_node, "replan", decision)
        self._advance(state)
        return self._view(state)
