"""Explicit dependency graph with entry/exit gates.

The graph is data (``NodeSpec``) plus behaviour: readiness, topological layers (the
parallelism the executor may exploit) and descendant lookup (the blast radius of a replan).
"""

from collections import deque
from dataclasses import dataclass


class GraphError(ValueError):
    pass


@dataclass(frozen=True)
class NodeSpec:
    id: str
    name: str
    kind: str  # "task" | "gate"
    depends_on: tuple[str, ...] = ()
    description: str = ""
    retryable: bool = True


DEFAULT_PLAN: tuple[NodeSpec, ...] = (
    NodeSpec("T1", "Requirement analysis", "task", (), "Interpret intent, detect ambiguity"),
    NodeSpec("T2", "Architecture & impact analysis", "task", ("T1",), "Scan code, find impact"),
    NodeSpec("T3", "Security & policy review", "task", ("T1",), "Evaluate policy guardrails"),
    NodeSpec("G1", "Implementation approval", "gate", ("T2", "T3"), "Human entry gate"),
    NodeSpec("T4", "Bounded implementation", "task", ("G1",), "Generate code and tests"),
    NodeSpec("T5", "Automated testing", "task", ("T4",), "Run the generated test suite"),
    NodeSpec("T6", "Documentation", "task", ("T4",), "Generate change notes"),
    NodeSpec(
        "T7",
        "Release-readiness validation",
        "task",
        ("T5", "T6"),
        "Check evidence",
        retryable=False,
    ),
    NodeSpec("G2", "Release approval", "gate", ("T7",), "Human exit gate"),
)


class DependencyGraph:
    def __init__(self, specs: tuple[NodeSpec, ...] = DEFAULT_PLAN):
        self._specs: dict[str, NodeSpec] = {}
        for spec in specs:
            if spec.id in self._specs:
                raise GraphError(f"Duplicate node id: {spec.id}")
            self._specs[spec.id] = spec
        for spec in specs:
            for dep in spec.depends_on:
                if dep not in self._specs:
                    raise GraphError(f"{spec.id} depends on unknown node {dep}")
        self._children: dict[str, list[str]] = {s.id: [] for s in specs}
        for spec in specs:
            for dep in spec.depends_on:
                self._children[dep].append(spec.id)
        self._layers = self._compute_layers()

    @property
    def specs(self) -> list[NodeSpec]:
        return list(self._specs.values())

    def spec(self, node_id: str) -> NodeSpec:
        if node_id not in self._specs:
            raise GraphError(f"Unknown node: {node_id}")
        return self._specs[node_id]

    def has(self, node_id: str) -> bool:
        return node_id in self._specs

    def ready(self, statuses: dict[str, str]) -> list[NodeSpec]:
        """Pending nodes whose dependencies have all completed."""
        return [
            spec
            for spec in self._specs.values()
            if statuses.get(spec.id, "pending") == "pending"
            and all(statuses.get(dep) == "completed" for dep in spec.depends_on)
        ]

    def descendants(self, node_id: str) -> set[str]:
        self.spec(node_id)
        seen: set[str] = set()
        queue = deque(self._children[node_id])
        while queue:
            current = queue.popleft()
            if current not in seen:
                seen.add(current)
                queue.extend(self._children[current])
        return seen

    def layers(self) -> list[list[str]]:
        return [list(layer) for layer in self._layers]

    def _compute_layers(self) -> list[list[str]]:
        indegree = {s.id: len(s.depends_on) for s in self._specs.values()}
        current = [node for node, degree in indegree.items() if degree == 0]
        layers: list[list[str]] = []
        visited = 0
        while current:
            layers.append(current)
            visited += len(current)
            following: list[str] = []
            for node in current:
                for child in self._children[node]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        following.append(child)
            current = following
        if visited != len(self._specs):
            raise GraphError("Dependency cycle detected")
        return layers

    def to_mermaid(self, statuses: dict[str, str] | None = None) -> str:
        statuses = statuses or {}
        lines = ["flowchart TD"]
        for spec in self._specs.values():
            status = statuses.get(spec.id, "pending")
            shape = ("{{", "}}") if spec.kind == "gate" else ("[", "]")
            lines.append(f'  {spec.id}{shape[0]}"{spec.id}: {spec.name} ({status})"{shape[1]}')
        for spec in self._specs.values():
            for dep in spec.depends_on:
                lines.append(f"  {dep} --> {spec.id}")
        return "\n".join(lines)
