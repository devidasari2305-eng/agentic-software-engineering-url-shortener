import re

from orchestrator.catalog import CAPABILITIES, detect_capabilities
from orchestrator.models import RequirementAnalysis
from orchestrator.providers.base import AIProvider

_VAGUE_TERMS = {
    "faster": "What measurable latency target (for example p95 in ms) defines 'faster', and for which endpoint?",
    "popular": "How is 'popular' defined (for example clicks within a time window)?",
    "scalable": "What load (requests per second, number of URLs, retention) must be sustained?",
    "better": "Which measurable outcome defines 'better'?",
    "improve": "Which metric should improve, and by how much?",
    "optimize": "Which resource or metric is being optimized, and what is the target?",
    "efficient": "What efficiency target (latency, cost, memory) is expected?",
    "robust": "Which failure modes must be tolerated?",
}  # fmt: skip

_HIGH_RISK = re.compile(
    r"\b(migration|schema|alter\s+table|breaking|production|credential\w*|delete|auth\w*|pii)\b",
    re.IGNORECASE,
)


class DeterministicProvider(AIProvider):
    """Rule-based analysis: reproducible, needs no API key, and is the fallback for AI providers."""

    name = "deterministic"

    def analyze_requirement(self, requirement: str, scenario: str) -> RequirementAnalysis:
        text = requirement.strip()
        capabilities = detect_capabilities(text, scenario)

        ambiguities = []
        has_numeric_target = bool(re.search(r"\d", text))
        for term, question in _VAGUE_TERMS.items():
            if re.search(rf"\b{term}\b", text, re.IGNORECASE) and not has_numeric_target:
                ambiguities.append(question)
        if len(text.split()) < 5:
            ambiguities.append("The requirement is very brief: what is the expected behaviour?")

        risks = ["Requirement drift", "Regression in existing behaviour"]
        criteria = []
        for name in capabilities:
            risks += CAPABILITIES[name]["risks"]
            criteria += CAPABILITIES[name]["acceptance_criteria"]

        return RequirementAnalysis(
            normalized_problem=text,
            capabilities=capabilities,
            ambiguities=ambiguities,
            assumptions=[
                "Backward compatibility with existing short URLs is required",
                "Agents may not deploy to production; humans own release decisions",
            ],
            risks=list(dict.fromkeys(risks)),
            acceptance_criteria=criteria,
            risk_level="high" if _HIGH_RISK.search(text) else "medium",
        )
