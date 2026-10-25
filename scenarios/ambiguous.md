# Scenario 3 - Ambiguous requirement

**Requirement:** "Make popular URLs faster"

`T1` finds undefined terms without a measurable target and stops with questions (latency target,
definition of "popular"). `T2`..`G2` never run, and approving the implementation gate is refused with
HTTP 409. A human answers via `POST /api/workflows/{id}/clarify` with measurable criteria
("Cache redirects for URLs with more than 100 clicks per hour for 60 seconds, targeting p95 redirect
latency under 50 ms"); the engine re-plans from T1 (plan v2) and proceeds to the gate.
