from typing import Literal

from pydantic import BaseModel, Field, field_validator

from orchestrator.catalog import CAPABILITIES

Scenario = Literal["greenfield", "brownfield", "ambiguous"]


class RequirementAnalysis(BaseModel):
    """Structured output every AI provider must return. Validated before it enters state."""

    normalized_problem: str
    capabilities: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "medium"

    @field_validator("capabilities")
    @classmethod
    def _known_capabilities(cls, value: list[str]) -> list[str]:
        known = [c for c in value if c in CAPABILITIES]
        return known or ["generic"]


class WorkflowRequest(BaseModel):
    requirement: str = Field(min_length=10, max_length=2000)
    scenario: Scenario
    requested_by: str = Field(default="anonymous", min_length=2, max_length=100)
    fault_injection: dict[str, int] | None = Field(
        default=None,
        description="Demo/test only. Map of task id to number of attempts that should fail, "
        "e.g. {'T5': 1} for a transient failure or {'T5': 99} to force rollback.",
    )


class ApprovalRequest(BaseModel):
    gate: Literal["implementation", "release"]
    approved: bool
    approver: str = Field(min_length=2, max_length=100)
    comment: str = Field(default="", max_length=2000)


class ClarificationRequest(BaseModel):
    clarified_requirement: str = Field(min_length=10, max_length=2000)
    author: str = Field(min_length=2, max_length=100)


class ReplanRequest(BaseModel):
    changed_node: str = Field(description="Upstream node whose output changed, e.g. T1 or T2")
    reason: str = Field(min_length=5, max_length=500)
    new_requirement: str | None = Field(default=None, min_length=10, max_length=2000)
    requested_by: str = Field(default="anonymous", min_length=2, max_length=100)
