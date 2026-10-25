"""End-to-end demonstration of the governed agentic orchestrator.

Runs every scenario against a real engine (real SQLite store, real workspaces, and a real pytest
subprocess executing the generated tests), prints the evidence a reviewer cares about, and
finishes with the reliability metrics and audit-integrity verdict.

    python demo.py
"""

import shutil
import sys
import time
from pathlib import Path

from orchestrator.engine import WorkflowEngine
from orchestrator.errors import InvalidTransition
from orchestrator.models import ApprovalRequest, WorkflowRequest
from orchestrator.store import WorkflowStore
from orchestrator.test_runner import PytestRunner

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "demo_output"

GREENFIELD = "Build a URL shortener API with click analytics and reliable redirects"
BROWNFIELD = "Add optional expiration to the existing URL shortener"
CHANGED = "Add expiration only for newly created URLs; existing URLs must never expire"
AMBIGUOUS = "Make popular URLs faster"
CLARIFIED = (
    "Cache redirects for URLs with more than 100 clicks per hour for 60 seconds, "
    "targeting p95 redirect latency under 50 ms"
)

ICONS = {
    "completed": "[x]",
    "pending": "[ ]",
    "awaiting_approval": "[?]",
    "blocked": "[!]",
    "failed": "[F]",
    "running": "[~]",
    "rejected": "[R]",
}


def banner(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def step(text: str) -> None:
    print(f"\n-> {text}")


def show(state: dict) -> None:
    nodes = " ".join(f"{nid}{ICONS.get(n['status'], '[?]')}" for nid, n in state["nodes"].items())
    print(f"   status : {state['status']}  (plan v{state['version']})")
    print(f"   graph  : {nodes}")


def approve(engine: WorkflowEngine, state: dict, gate: str, comment: str = "Reviewed") -> dict:
    step(f"Human approves the {gate} gate")
    state = engine.approve(
        state["id"],
        ApprovalRequest(gate=gate, approved=True, approver="Venkatesh Panjala", comment=comment),
    )
    show(state)
    return state


def main() -> int:
    shutil.rmtree(OUT, ignore_errors=True)
    engine = WorkflowEngine(
        store=WorkflowStore(f"sqlite:///{(OUT / 'workflows.db').as_posix()}"),
        workspace_root=OUT / "workspaces",
        repo_root=ROOT,
        test_runner=PytestRunner(timeout_seconds=120),
        max_retries=2,
        retry_backoff_ms=20,
    )
    started = time.perf_counter()
    print("Layers the executor may run in parallel:", engine.graph.layers())

    # ------------------------------------------------------------------ 1. greenfield
    banner("SCENARIO 1 - GREENFIELD: requirement -> plan -> code -> real tests -> release")
    state = engine.start(WorkflowRequest(requirement=GREENFIELD, scenario="greenfield"))
    analysis = state["outputs"]["T1"]
    print(f"   capabilities identified : {analysis['capabilities']}")
    print(f"   proposed components     : {len(state['outputs']['T2']['components'])}")
    show(state)
    state = approve(engine, state, "implementation")
    print(f"   generated files         : {state['outputs']['T4']['files']}")
    print(f"   real pytest run         : {state['outputs']['T5']['passed']} passed")
    print(
        f"   T5/T6 ran concurrently  : {state['nodes']['T5']['parallel_group']}"
        f" == {state['nodes']['T6']['parallel_group']}"
    )
    state = approve(engine, state, "release")
    print(f"   engineering summary     : {state['outputs']['T7']['summary_document']}")

    # ------------------------------------------------------------------ 2. brownfield
    banner("SCENARIO 2 - BROWNFIELD: real code analysis + dynamic re-planning")
    state = engine.start(WorkflowRequest(requirement=BROWNFIELD, scenario="brownfield"))
    impact = state["outputs"]["T2"]["impact"]
    print(f"   modules scanned (ast)   : {impact['modules_scanned']}")
    print(f"   directly impacted       : {[m['module'] for m in impact['direct_modules']]}")
    print(f"   transitively impacted   : {[m['module'] for m in impact['dependent_modules']]}")
    print(f"   data flow example       : {impact['data_flows'][0]}")
    print(f"   notes                   : {state['outputs']['T2']['notes'][-1]}")
    show(state)

    step("Upstream output changed: impact analysis (T2) is stale -> partial re-plan")
    state = engine.replan(state["id"], "T2", "Impact analysis refreshed after merge")
    decision = state["decisions"][-1]
    print(f"   invalidated : {decision['invalidated']}")
    print(f"   preserved   : {decision['preserved']}  (reused, not recomputed)")
    show(state)

    step("Product owner changes the requirement -> re-plan from T1")
    state = engine.replan(state["id"], "T1", "Scope changed by product owner", CHANGED)
    decision = state["decisions"][-1]
    print(f"   requirement : {decision['requirement_change']['to']}")
    print(f"   invalidated : {decision['invalidated']}")
    print(
        f"   version     : {decision['from_version']} -> {decision['to_version']}"
        f"  | history entries kept: {len(state['history'])}"
    )
    state = approve(engine, state, "implementation")
    state = approve(engine, state, "release")

    # ------------------------------------------------------------------ 3. ambiguous
    banner("SCENARIO 3 - AMBIGUOUS: the agent stops instead of guessing")
    state = engine.start(WorkflowRequest(requirement=AMBIGUOUS, scenario="ambiguous"))
    show(state)
    for question in state["outputs"]["T1"]["ambiguities"]:
        print(f"   ? {question}")
    step("Try to approve implementation while ambiguity is unresolved")
    try:
        engine.approve(
            state["id"],
            ApprovalRequest(gate="implementation", approved=True, approver="Reviewer"),
        )
    except InvalidTransition as error:
        print(f"   refused: {error}")
    step("Product owner answers with measurable criteria")
    state = engine.clarify(state["id"], CLARIFIED, "Product Owner")
    print(f"   capabilities now: {state['outputs']['T1']['capabilities']}")
    show(state)
    state = approve(engine, state, "implementation")
    state = approve(engine, state, "release")

    # ------------------------------------------------------------------ 4. reliability
    banner("SCENARIO 4 - RELIABILITY: retry, fallback, rollback, policy safe-stop")

    step("4a. Transient failure in T5 (1 injected) -> bounded retry recovers")
    state = engine.start(
        WorkflowRequest(requirement=GREENFIELD, scenario="greenfield", fault_injection={"T5": 1})
    )
    state = approve(engine, state, "implementation")
    incident = state["incidents"][0]
    print(
        f"   attempts={state['nodes']['T5']['attempts']} incident={incident['kind']}"
        f" mttr={incident['mttr_ms']} ms"
    )
    state = approve(engine, state, "release")

    step("4b. AI provider outage in T1 (every attempt fails) -> deterministic fallback")
    state = engine.start(
        WorkflowRequest(requirement=GREENFIELD, scenario="greenfield", fault_injection={"T1": 99})
    )
    print(
        f"   T1 resolved via: {state['nodes']['T1']['via']} -> {state['outputs']['T1']['provider']}"
    )
    state = approve(engine, state, "implementation")
    state = approve(engine, state, "release")

    step("4c. Persistent failure in T5 -> retries exhausted -> checkpoint rollback -> safe-stop")
    state = engine.start(
        WorkflowRequest(requirement=GREENFIELD, scenario="greenfield", fault_injection={"T5": 99})
    )
    state = approve(engine, state, "implementation")
    files = engine.artifacts(state["id"])["files"]
    print(f"   retries={state['counters']['retries']} rollbacks={state['counters']['rollbacks']}")
    print(f"   workspace restored to checkpoint, files now: {sorted(files)}")
    print(
        f"   incident: {state['incidents'][0]['kind']} mttr={state['incidents'][0]['mttr_ms']} ms"
    )

    step("4d. Requirement that asks an agent to deploy to production -> policy block")
    state = engine.start(
        WorkflowRequest(
            requirement="Deploy the redirect cache directly to production",
            scenario="brownfield",
        )
    )
    show(state)
    print(f"   reason: {state['nodes']['T3']['error']}")
    print(f"   T3 attempts: {state['nodes']['T3']['attempts']} (non-retryable)")

    # ------------------------------------------------------------------ evidence
    banner("EVIDENCE - reliability metrics and audit integrity")
    metrics = engine.metrics()
    for key in (
        "total_workflows",
        "succeeded",
        "safe_stopped",
        "success_rate_pct",
        "retries",
        "fallbacks",
        "rollbacks",
        "replans",
        "mttr_ms",
        "mttr_ms_by_outcome",
        "avg_end_to_end_latency_ms",
        "avg_agent_execution_ms",
    ):
        print(f"   {key:28}: {metrics[key]}")
    verdicts = [engine.audit(w["id"])["integrity"] for w in engine.list_workflows()]
    print(f"   audit chains verified      : {sum(v['valid'] for v in verdicts)}/{len(verdicts)}")
    print(f"\nDone in {time.perf_counter() - started:.1f}s. Artifacts are in {OUT}")
    return 0 if all(v["valid"] for v in verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
