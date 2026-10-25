# Scenario 1 - Greenfield

**Requirement:** "Build a URL shortener API with click analytics and reliable redirects"

| Stage | What happens |
|---|---|
| T1 | Capabilities `shortening`, `analytics`; no ambiguity; acceptance criteria derived |
| T2 + T3 (parallel) | Proposed components; 7 policy rules evaluated, none block |
| G1 | Human approval; pre-implementation checkpoint taken |
| T4 | `shortcode.py`, `click_counter.py` and their tests generated after a code policy scan |
| T5 + T6 (parallel) | Real pytest run (7 passed); change notes generated |
| T7 | Release checks pass; engineering summary written |
| G2 | Human release approval -> `release_ready` |

Run: `python demo.py` (scenario 1) or `POST /api/workflows` with `"scenario": "greenfield"`.
