# Scenario 2 - Brownfield and dynamic re-planning

**Requirement:** "Add optional expiration to the existing URL shortener"

`T2` scans this repository with `ast`: directly impacted `app.api.urls`, `app.models.url`,
`app.schemas.url`, `app.services.url_service`; transitively `app.main`, `app.models`; the data flows
(for example `app.api.urls -> app.services.url_service -> app.models.url`), the affected routes and
the tests to review. It also notes that `expires_at` already exists, so no schema migration is needed.

**Re-planning, two kinds**

1. *Upstream output changed (T2 stale):* `invalidated = G1,G2,T2,T4,T5,T6,T7`, `preserved = T1,T3`.
   T3's output is reused untouched.
2. *Requirement changed* ("only newly created URLs may expire; existing URLs never expire"):
   re-plan from T1; everything downstream is invalidated, the plan version increments, superseded
   outputs are archived, and the human gate re-opens.
