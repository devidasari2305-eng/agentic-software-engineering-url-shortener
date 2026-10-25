# Agentic Software Engineering System - URL Shortener

## Overview

This project is my implementation of an *Agentic Software Engineering System*, using a URL shortener as the sample application.

I intentionally kept the URL shortener relatively simple and focused more on the orchestration requirements of the assignment.

The main goal was to build a workflow that can:

- understand an engineering requirement
- identify ambiguity and assumptions
- identify impacted components for an existing application
- break work into dependent activities
- run independent activities in parallel where possible
- require human approval before important actions
- generate implementation artifacts
- run automated tests
- generate documentation
- handle failures through retries and rollback
- maintain an audit trail
- dynamically re-plan when an earlier requirement or decision changes

The solution is designed around *controlled autonomy*. Agents can analyze, plan, generate artifacts, test and document changes, but humans remain responsible for implementation and release approvals.

---

## Solution Architecture

The workflow is organized into the following stages:

text
Requirement
    |
    v
T1 - Requirement Analysis
    |
    +----------------+
    |                |
    v                v
T2 - Architecture   T3 - Security / Policy Review
    |                |
    +-------+--------+
            |
            v
     G1 - Human Approval
            |
            v
     T4 - Implementation
            |
       +----+----+
       |         |
       v         v
 T5 - Testing   T6 - Documentation
       |         |
       +----+----+
            |
            v
     T7 - Release Validation
            |
            v
     G2 - Human Approval
            |
            v
       Release Ready


### Why I used this approach

I wanted the dependencies between engineering activities to be explicit instead of building a simple sequence of agent calls.

For example:

- Architecture and security analysis both depend on requirement analysis, so they can run independently.
- Implementation cannot start until both are complete and the implementation approval gate is approved.
- Testing and documentation can run in parallel after implementation.
- Release validation waits for both testing and documentation.

This gives the workflow a clear dependency model and also makes dynamic re-planning possible.

---

## Project Structure

text
app/
    api/                 FastAPI endpoints
    core/                Configuration and database setup
    models/              Database models
    schemas/             API request/response models
    services/            URL shortener business logic

orchestrator/
    agents/              SDLC agents
    providers/           AI provider abstraction
    engine.py            Workflow execution engine
    graph.py             Dependency graph
    codebase.py          Brownfield code analysis
    policy.py            Security and change-control policies
    workspace.py         Generated artifact workspace/checkpoints
    store.py             Persistent workflow state and audit log
    metrics.py           Reliability metrics

tests/                   Automated tests
scenarios/               Assignment demonstration scenarios
docs/                    Architecture and design documentation
demo.py                  End-to-end demonstration


---

## Model and Data Separation

I kept the application models, API contracts and orchestration models separate instead of placing everything in a single model file.

- app/models/url.py contains the SQLAlchemy persistence models for ShortURL and ClickEvent.
- app/schemas/url.py contains the API request and response contracts.
- orchestrator/models.py contains the structured models used by the agentic workflow, including requirements, approvals, clarification and re-planning requests.
- orchestrator/store.py contains the persistence structures used for workflow state and audit history.

I chose this separation so that API contracts, database entities and orchestration state can evolve independently without tightly coupling the layers.

# URL Shortener

The URL shortener is the application used to demonstrate both greenfield and brownfield engineering scenarios.

## APIs

| Method | API | Purpose |
|---|---|---|
| POST | /api/urls | Create a short URL |
| GET | /{code} | Redirect to the original URL |
| GET | /api/urls/{code} | Retrieve URL details |
| GET | /api/urls/{code}/analytics | View click analytics |
| DELETE | /api/urls/{code} | Disable a short URL |
| GET | /health | Application health check |

The implementation includes:

- generated or custom short codes
- collision handling
- optional expiration
- disabled URL handling
- click tracking
- input validation
- bounded code-generation attempts

---

# Agentic Workflow

## T1 - Requirement Analysis

The first stage analyzes the incoming requirement.

The output contains:

- normalized requirement
- identified capabilities
- ambiguities
- assumptions
- risks
- acceptance criteria
- overall risk level

For example, a requirement such as:

> Add optional expiration to the existing URL shortener.

is identified as an *expiration* capability and passed to the architecture and security stages.

If the requirement is unclear, the workflow stops rather than making assumptions.

---

## T2 - Architecture and Impact Analysis

For brownfield changes, I wanted the workflow to reason about the existing application rather than return a hard-coded list of impacted components.

The project therefore uses Python's ast module to inspect the codebase.

The analysis can identify:

- modules
- imports
- functions/classes
- API routes
- directly impacted modules
- dependent modules
- possible data flows
- tests that should be reviewed

For example, an expiration change can identify impact around:

text
app.models.url
app.schemas.url
app.services.url_service
app.api.urls


This provides evidence for the change plan before implementation begins.

---

## T3 - Security and Policy Review

The orchestration layer has policy rules to limit what an agent is allowed to do.

Policy results can be:

text
ALLOW
REQUIRE APPROVAL
BLOCK


Examples of blocked activities include:

- autonomous production deployment
- bypassing approval controls
- destructive data operations
- unsafe generated-code patterns
- hard-coded secrets

This is one of the ways the application implements controlled autonomy.

---

# Human Approval Gates

I use two approval gates.

## G1 - Implementation Approval

Implementation does not start automatically after planning.

Architecture and security analysis must first complete, after which the workflow pauses for human review.

For higher-risk changes, the reviewer must also provide a comment acknowledging the risk.

A checkpoint is created after approval so the workflow has a known state to return to if later execution fails.

## G2 - Release Approval

Passing automated tests does not automatically release the change.

After validation completes, a second human approval is required.

The final state is:

text
release_ready


The prototype deliberately does not provide an autonomous production-deployment capability.

---

# Implementation Workspace

Generated implementation artifacts are written to a separate workflow workspace:

text
workspaces/{workflow-id}/


They are not automatically written into or merged into the main source code.

A workspace can contain:

text
src/
tests/
analysis/
docs/
reports/
release/


This provides a boundary between what an agent generates and what eventually becomes part of the application.

---

# Automated Testing

The testing stage executes generated tests using a real pytest subprocess.

The workflow therefore does not simply accept an agent statement such as:

> Tests passed.

Instead:

text
Generated implementation
        |
        v
Generated tests
        |
        v
pytest execution
        |
        v
Test report
        |
        v
Release validation


The repository itself also contains automated tests for the orchestration system, policy rules, dependency graph, rollback behavior, persistence and APIs.

Run:

bash
python -m pytest -q


---

# Retry, Fallback and Rollback

I treat retry, fallback and rollback as separate concepts.

## Retry

A temporary failure causes the same task to run again up to the configured retry limit.

Example:

text
Testing
   |
failure
   |
Retry
   |
success


## Fallback

If the configured AI provider fails after its retry limit, requirement analysis can fall back to the deterministic provider.

This allows the workflow to degrade gracefully rather than depending completely on an external AI service.

## Rollback

Before implementation begins, a checkpoint is created.

If an implementation-stage failure continues after the retry limit is exhausted:

text
Failure
   |
Retries exhausted
   |
Restore checkpoint
   |
Reset affected tasks
   |
Safe stop


The workflow records the rollback rather than reporting the failed execution as successful.

---

# Dynamic Re-planning

A requirement or upstream engineering decision can change after a workflow has already started.

Instead of rerunning the entire workflow, the dependency graph determines what is affected.

For example, if the architecture stage changes:

text
T2 changed


the workflow can invalidate downstream activities such as:

text
G1
T4
T5
T6
T7
G2


while preserving independent work such as:

text
T1
T3


Superseded outputs are kept in workflow history and the plan version is incremented.

If the actual requirement changes, re-planning starts from T1 because everything downstream may be affected.

---

# Audit and Traceability

Workflow state is persisted rather than existing only in memory.

Important events are stored in the audit log, including:

- workflow creation
- task start/completion
- failed attempts
- retries
- approval decisions
- checkpoint creation
- rollback
- safe-stop
- re-planning
- workflow completion

Audit events are hash-chained so the application can detect modifications to previously stored audit events.

The audit API is:

text
GET /api/workflows/{id}/audit


---

# Reliability Metrics

The orchestration system collects metrics including:

- workflow success rate
- retries
- retry frequency
- fallbacks
- rollbacks
- rollback frequency
- re-plans
- MTTR
- end-to-end workflow latency
- agent execution time

Metrics are available at:

text
GET /api/workflows/metrics


For this prototype, MTTR represents the time between the first failed attempt and recovery through a successful retry, fallback or completed rollback.

---
# Demonstration Scenarios

The project includes the three main scenarios requested by the assignment, plus an additional failure-recovery demonstration.

## 1. Greenfield

Example:

> Build a URL shortener API with click analytics and reliable redirects.

This demonstrates the complete workflow from requirement analysis through release readiness.

---

## 2. Brownfield

Example:

> Add optional expiration to the existing URL shortener.

The existing codebase is analyzed to identify impacted modules and dependencies.

The scenario also demonstrates a requirement change such as:

> Existing URLs must never expire. Expiration should be optional only for newly created URLs.

The workflow identifies affected downstream activities and creates a revised plan.

---

## 3. Ambiguous Requirement

Example:

> Make popular URLs faster.

The system does not immediately implement caching.

Instead, it asks questions such as:

- What defines a popular URL?
- What latency target is expected?

After measurable criteria are provided, the workflow resumes with a new plan version.

---

## 4. Failure and Recovery

The demo also intentionally injects failures to demonstrate:

text
Transient failure -> Retry -> Recovery

AI provider failure -> Retry -> Fallback

Persistent implementation failure
    -> Retry exhaustion
    -> Rollback
    -> Safe stop

Policy violation
    -> Immediate safe stop


Fault injection exists only for demonstration and testing.

---

# AI Provider Design

The orchestration layer uses an AIProvider abstraction.

The default implementation is:

text
DeterministicProvider


This allows reviewers to run the complete project without needing an API key.

An optional:

text
OpenAICompatibleProvider


demonstrates where an external model can be integrated.

I intentionally kept the orchestration, policy enforcement, approval process, rollback and audit behaviour independent of a specific model.

For implementation generation, this prototype uses deterministic capability templates. This keeps execution reproducible and allows generated code to be tested reliably.

A production version could replace the implementation generator with a model-driven generator while keeping the same workspace, policy, validation and human-approval controls.

---

# Running the Project

## Prerequisites

- Python 3.12+
- Git
- Optional: Docker Desktop

No AI API key is required for the default configuration.

---

## Windows

Create a virtual environment:

powershell
py -m venv .venv


Activate:

powershell
.venv\Scripts\Activate.ps1


Install dependencies:

powershell
py -m pip install -r requirements.txt


Run tests:

powershell
py -m pytest -q


Run the assessment demo:

powershell
py demo.py


Start the API:

powershell
py -m uvicorn app.main:app --reload


Open Swagger:

text
http://127.0.0.1:8000/docs


Health:

text
http://127.0.0.1:8000/health


---

# Reviewer Demo

The simplest way to review the project is:

bash
python -m pytest -q
python demo.py
python -m uvicorn app.main:app --reload


Then open:

text
http://127.0.0.1:8000/docs


I recommend reviewing the scenarios in this order:

1. Greenfield workflow
2. Brownfield impact analysis
3. Dynamic re-planning
4. Ambiguous-require
5. Retry and fallback
6. Rollback
7. Audit trail
8. Reliability metrics

---

# Assumptions and Limitations

This is a prototype built for the assessment rather than a complete production platform.

Some deliberate limitations are:

- SQLite is used to keep setup simple.
- Workflow execution is single-process.
- Generated artifacts are not automatically merged into the main repository.
- Approver identity is supplied by the caller rather than verified through an identity provider.
- Brownfield impact analysis is static and may not detect dynamic runtime dependencies.
- The default AI provider is deterministic to keep the solution reproducible without credentials.
- Production deployment is intentionally outside agent authority.

For a production implementation, I would consider:

- PostgreSQL for durable workflow/application data
- Temporal or a similar durable workflow platform
- Redis for high-volume redirect caching
- OpenTelemetry for distributed tracing
- OIDC/RBAC for verified approvals
- protected CI/CD environments
- SAST, DAST and SBOM generation
- centralized immutable audit storage
- model-driven code generation behind the same policy and validation controls

---

# Key Design Decision

The main principle behind this implementation is:

> *Agents can reason and execute within defined boundaries, but humans retain control over consequential engineering decisions.*

The URL shortener demonstrates the engineering domain, while the orchestration layer demonstrates how requirement analysis, planning, implementation, validation, failure recovery and governance can work together in an agentic SDLC.