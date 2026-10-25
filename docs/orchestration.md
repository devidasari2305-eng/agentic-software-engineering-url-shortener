# Orchestration model

## Dependency graph

| Node | Depends on | Kind | Retryable | Notes |
|---|---|---|---|---|
| T1 Requirement analysis | - | task | yes | AI provider, falls back to deterministic |
| T2 Architecture & impact | T1 | task | yes | `ast` scan of the real repository |
| T3 Security & policy | T1 | task | yes | policy violations are non-retryable |
| G1 Implementation approval | T2, T3 | gate | - | human; takes the checkpoint |
| T4 Bounded implementation | G1 | task | yes | code policy scan before writing |
| T5 Automated testing | T4 | task | yes | real pytest subprocess |
| T6 Documentation | T4 | task | yes | runs in parallel with T5 |
| T7 Release validation | T5, T6 | task | **no** | produces the engineering summary |
| G2 Release approval | T7 | gate | - | human |

Parallel layers: `[T1] [T2 T3] [G1] [T4] [T5 T6] [T7] [G2]`.

## Failure handling

| Failure | Response |
|---|---|
| Transient agent error | retry with exponential backoff, up to `MAX_RETRIES` |
| AI provider error, retries exhausted | **fallback** to the deterministic provider (T1) |
| T4/T5/T6 still failing | **rollback** to the checkpoint, reset T4-G2, `safe_stopped_rolled_back` |
| Failure before the checkpoint | `safe_stopped_failure`, no rollback needed |
| Policy violation | `safe_stopped_policy`, never retried; if after the checkpoint, also rolled back |
| Release check fails (T7) | `safe_stopped_validation`, artifacts kept for review, never retried |
| Material ambiguity | `awaiting_clarification`, nothing downstream runs |

A human recovers any safe-stop with `replan` (for example from `T4` after fixing infrastructure;
the gate approval and earlier results are preserved).

## Dynamic re-planning

`replan(changed_node)` computes `invalidated = {node} + descendants` and
`preserved = completed nodes outside that set`, then:

1. archives each invalidated output in `history` (decision lineage),
2. deletes the artifacts those nodes produced,
3. resets the nodes (and gates) to `pending`; clears the checkpoint if `G1` was invalidated,
4. increments the plan version and records a `dynamic_replan` decision (reason, requester,
   invalidated, preserved, requirement diff),
5. re-enters the loop, which stops again at `G1`, so a human re-approves.

A requirement change must start at `T1`; a changed upstream output (for example `T2`) re-plans only
its branch. Replans are counted separately from rollbacks.

## Audit events

`workflow_created`, `batch_started`, `node_started`, `attempt_failed`, `fallback_used`,
`node_completed`, `node_failed`, `gate_opened`, `approval_recorded`, `checkpoint_created`,
`awaiting_clarification`, `rollback_completed`, `safe_stop`, `replan`, `status_changed`,
`workflow_completed`. Each row stores `prev_hash` and `hash = SHA256(prev | seq | ts | node | event |
detail)`; verification recomputes the chain.

## Metrics definitions

- **Success rate**: `release_ready` / workflows in a terminal state.
- **Retry / rollback frequency**: totals, retries per workflow, rollbacks as a share of workflows.
- **MTTR**: first failed attempt to recovery (retry success, fallback success, or completed
  rollback). Unrecovered failures are counted as incidents but excluded from the mean.
- **End-to-end latency**: creation to terminal state, *including* human wait time.
- **Agent execution time**: wall-clock time of agent batches only.
