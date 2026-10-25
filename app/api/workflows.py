from functools import lru_cache

from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from orchestrator.bootstrap import build_engine
from orchestrator.engine import WorkflowEngine
from orchestrator.models import (
    ApprovalRequest,
    ClarificationRequest,
    ReplanRequest,
    WorkflowRequest,
)

router = APIRouter(prefix="/api/workflows", tags=["agentic workflows"])


@lru_cache
def get_engine() -> WorkflowEngine:
    return build_engine(settings)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Start a governed workflow")
def start(payload: WorkflowRequest, engine: WorkflowEngine = Depends(get_engine)):
    return engine.start(payload)


@router.get("", summary="List workflows")
def list_workflows(engine: WorkflowEngine = Depends(get_engine)):
    return engine.list_workflows()


@router.get("/metrics", summary="Reliability metrics across all workflows")
def metrics(engine: WorkflowEngine = Depends(get_engine)):
    return engine.metrics()


@router.get("/{workflow_id}", summary="Workflow state, graph status, decisions and incidents")
def get_workflow(workflow_id: str, engine: WorkflowEngine = Depends(get_engine)):
    return engine.get(workflow_id)


@router.get("/{workflow_id}/graph", summary="Dependency graph with live node status")
def graph(workflow_id: str, engine: WorkflowEngine = Depends(get_engine)):
    return engine.graph_view(workflow_id)


@router.get("/{workflow_id}/audit", summary="Hash-chained audit log with integrity verdict")
def audit(workflow_id: str, engine: WorkflowEngine = Depends(get_engine)):
    return engine.audit(workflow_id)


@router.get("/{workflow_id}/artifacts", summary="Generated files with SHA-256 digests")
def artifacts(workflow_id: str, engine: WorkflowEngine = Depends(get_engine)):
    return engine.artifacts(workflow_id)


@router.get(
    "/{workflow_id}/summary",
    response_class=PlainTextResponse,
    summary="Final engineering summary (markdown)",
)
def summary(workflow_id: str, engine: WorkflowEngine = Depends(get_engine)):
    return engine.summary_document(workflow_id)


@router.post("/{workflow_id}/approval", summary="Human decision at the implementation/release gate")
def approve(
    workflow_id: str, payload: ApprovalRequest, engine: WorkflowEngine = Depends(get_engine)
):
    return engine.approve(workflow_id, payload)


@router.post(
    "/{workflow_id}/clarify", summary="Answer clarification questions (ambiguity safe-stop)"
)
def clarify(
    workflow_id: str, payload: ClarificationRequest, engine: WorkflowEngine = Depends(get_engine)
):
    return engine.clarify(workflow_id, payload.clarified_requirement, payload.author)


@router.post(
    "/{workflow_id}/replan", summary="Re-plan after an upstream output or requirement changes"
)
def replan(workflow_id: str, payload: ReplanRequest, engine: WorkflowEngine = Depends(get_engine)):
    return engine.replan(
        workflow_id,
        payload.changed_node,
        payload.reason,
        payload.new_requirement,
        payload.requested_by,
    )
