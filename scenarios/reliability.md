# Scenario 4 - Reliability and safety

Use `fault_injection` on `POST /api/workflows` (demo/test only).

| Case | Request | Expected |
|---|---|---|
| Transient failure | `{"T5": 1}` | 2 attempts, incident `recovered`, MTTR recorded, workflow continues |
| AI provider outage | `{"T1": 99}` | retries exhausted, T1 completes via the deterministic fallback |
| Persistent failure | `{"T5": 99}` | 2 retries, rollback to checkpoint, `safe_stopped_rolled_back`; workspace holds only the analysis files |
| Policy violation | requirement "Deploy ... directly to production" | `safe_stopped_policy` at T3, one attempt, no retries |

Recover from a safe-stop with `POST /api/workflows/{id}/replan` (for example `changed_node: "T4"`).
