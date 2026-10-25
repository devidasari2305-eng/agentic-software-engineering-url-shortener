from abc import ABC, abstractmethod

from orchestrator.models import RequirementAnalysis


class AIProvider(ABC):
    """Stable boundary between orchestration and any reasoning model.

    Providers return a validated ``RequirementAnalysis``. The orchestrator never trusts raw
    model text: output is schema-validated, then policy-checked, before it enters workflow state.
    """

    name = "provider"

    @abstractmethod
    def analyze_requirement(self, requirement: str, scenario: str) -> RequirementAnalysis: ...
