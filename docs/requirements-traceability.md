# Requirement traceability

Maps each statement in the assignment to the implementation and the test that proves it.

| Requirement | Implementation | Evidence (tests) |
|---|---|---|
| Requirement understanding, ambiguity, normalisation | `providers/deterministic.py`, `models.RequirementAnalysis` | `test_ambiguous_requirement_safe_stops_and_cannot_be_approved` |
| Task decomposition with dependencies | `graph.DEFAULT_PLAN` | `test_default_plan_layers_expose_parallel_branches` |
| Brownfield codebase reasoning | `codebase.py`, `agents/architecture.py` | `test_expiration_impact_is_derived_from_real_code`, `test_routes_include_router_prefix` |
| Explicit dependency graph, entry/exit gates | `graph.py`, gates `G1`/`G2` | `test_ready_requires_all_dependencies_completed`, `test_cycle_is_rejected` |
| Sequential and parallel paths with synchronisation | `engine._run_batch` | `test_architecture_and_security_run_concurrently`, `test_tests_and_documentation_run_concurrently` |
| Cross-stage context and decision lineage | `state["outputs"]`, `decisions`, `history` | `test_upstream_output_change_replans_only_the_affected_branch` |
| Human approval for high-impact actions | `engine.approve`, policy `requires_comment` | `test_high_impact_change_requires_a_risk_acknowledgement_comment`, `test_approvals_must_come_from_a_named_human` |
| Bounded retries | `engine._run_node` | `test_transient_failure_is_retried_and_recovers` |
| Fallback | `fallbacks["T1"]` | `test_ai_provider_failure_falls_back_to_deterministic_provider` |
| Rollback | `engine._rollback`, `workspace.restore` | `test_exhausted_retries_roll_back_to_checkpoint_and_safe_stop`, `test_a_genuinely_failing_test_triggers_retry_rollback_and_safe_stop` |
| Safe-stop | `_handle_failure`, `_check_ambiguity` | `test_policy_violation_safe_stops_without_retries`, `test_failure_before_the_checkpoint_safe_stops_without_rollback` |
| Policy guardrails (security, compliance, change control) | `policy.py` | `tests/test_policy.py` |
| Audit-grade observability and traceability | `store.py` | `test_audit_log_is_complete_and_tamper_evident`, `test_audit_tampering_is_detected` |
| Reliability metrics (success, retry/rollback, MTTR, latency) | `metrics.py` | `test_reliability_metrics_aggregate_across_workflows`, `tests/test_metrics.py` |
| Dynamic re-planning | `engine._replan` | `test_requirement_change_invalidates_everything_downstream`, `test_replan_after_implementation_removes_stale_artifacts_and_reopens_the_gate` |
| Production-quality code, API/schema, tests, docs | `app/`, Pydantic schemas, OpenAPI, `tests/`, `docs/` | full suite, `ruff` in CI |
| Validation and risk control | `agents/release.py`, policy scan | `test_failing_release_validation_is_not_retried` |
| Controlled autonomy | gates, workspace sandbox, non-retryable policy errors | `test_path_traversal_and_checkpoint_writes_are_blocked` |
| Final engineering summary | `agents/release.py` -> `release/engineering-summary.md` | `test_brownfield_expiration_is_generated_tested_and_released` |
| Three scenarios | `demo.py`, `scenarios/` | `python demo.py` |
| Durability / restart | `store.py` | `test_workflow_survives_an_engine_restart` |
