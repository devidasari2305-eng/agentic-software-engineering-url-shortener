import pytest

from orchestrator.graph import DependencyGraph, GraphError, NodeSpec


def test_default_plan_layers_expose_parallel_branches():
    layers = DependencyGraph().layers()
    assert layers[0] == ["T1"]
    assert sorted(layers[1]) == ["T2", "T3"]
    assert layers[2] == ["G1"]
    assert sorted(layers[4]) == ["T5", "T6"]


def test_ready_requires_all_dependencies_completed():
    graph = DependencyGraph()
    statuses = {"T1": "completed"}
    assert sorted(s.id for s in graph.ready(statuses)) == ["T2", "T3"]
    statuses["T2"] = "completed"
    assert "G1" not in [s.id for s in graph.ready(statuses)]
    statuses["T3"] = "completed"
    assert [s.id for s in graph.ready(statuses)] == ["G1"]


def test_ready_ignores_nodes_that_are_not_pending():
    graph = DependencyGraph()
    statuses = {"T1": "completed", "T2": "running", "T3": "failed"}
    assert graph.ready(statuses) == []


def test_descendants_define_replan_blast_radius():
    graph = DependencyGraph()
    assert graph.descendants("T2") == {"G1", "T4", "T5", "T6", "T7", "G2"}
    assert "T3" not in graph.descendants("T2")
    assert graph.descendants("G2") == set()


def test_cycle_is_rejected():
    specs = (NodeSpec("A", "a", "task", ("B",)), NodeSpec("B", "b", "task", ("A",)))
    with pytest.raises(GraphError, match="cycle"):
        DependencyGraph(specs)


def test_unknown_dependency_and_duplicates_are_rejected():
    with pytest.raises(GraphError, match="unknown"):
        DependencyGraph((NodeSpec("A", "a", "task", ("Z",)),))
    with pytest.raises(GraphError, match="Duplicate"):
        DependencyGraph((NodeSpec("A", "a", "task"), NodeSpec("A", "again", "task")))


def test_mermaid_contains_edges_and_status():
    text = DependencyGraph().to_mermaid({"T1": "completed"})
    assert "T1 --> T2" in text and "(completed)" in text
