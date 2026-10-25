import json
from dataclasses import dataclass
from typing import Any

from orchestrator.codebase import CodebaseAnalyzer
from orchestrator.policy import PolicyEngine
from orchestrator.providers.base import AIProvider
from orchestrator.workspace import Workspace


@dataclass
class NodeContext:
    """Read-only snapshot handed to an agent, plus the sandboxed workspace it may write to."""

    workflow_id: str
    requirement: str
    scenario: str
    version: int
    outputs: dict[str, dict]
    workspace: Workspace
    provider: AIProvider
    fallback_provider: AIProvider
    policy: PolicyEngine
    analyzer: CodebaseAnalyzer
    test_runner: Any
    checkpoint: dict | None
    counters: dict
    incidents: list
    nodes: dict
    decisions: list

    def output(self, node_id: str) -> dict:
        return self.outputs[node_id]


def to_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, default=str) + "\n"
