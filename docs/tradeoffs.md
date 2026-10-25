# Trade-offs, assumptions and limitations

## Deliberate trade-offs

| Choice | Benefit | Cost |
|---|---|---|
| Deterministic provider by default | Reproducible, no secret, ideal for review | Requirement analysis is rule-based unless `AI_PROVIDER=openai` |
| Template-based code generation | Reviewable, every template ships with tests that really run | Narrow: four capabilities (shortening, expiration, caching, analytics); anything else gets a traceable stub |
| SQLite for stores | Zero setup | Single writer; not for high concurrency |
| In-process locks and thread pool | Simple, correct for one process | Cannot scale horizontally |
| Generated code stays in a workspace | Strong safety boundary | A human must merge it |
| Static `ast` impact analysis | Fast, explainable | Misses dynamic dispatch and runtime wiring |

## Assumptions

Backward compatibility with existing short URLs is required; humans own release decisions;
approver identity is supplied by the caller.

## Known limitations

- A process crash *during* a batch leaves the workflow in `running`; completed transitions are
  durable, but resuming a half-executed batch is not implemented.
- `GET /api/workflows/metrics` aggregates by loading all workflow rows (fine at prototype scale).
- The OpenAI adapter is tested against a mocked HTTP layer (response validation and outage
  fallback); it has not been exercised against the live API in CI.
- Click analytics are synchronous with the redirect.

## Production evolution

PostgreSQL, a durable workflow engine (Temporal or equivalent) for crash-resumable batches and
distributed workers, a model-driven code generator behind the same policy scan and test gate,
OIDC/RBAC with signed approvals, Redis for hot redirects, an event stream for analytics,
OpenTelemetry for tracing, and externally anchored audit storage.
