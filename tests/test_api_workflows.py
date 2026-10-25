from tests.helpers import AMBIGUOUS, CLARIFIED, GREENFIELD


def _start(client, text=GREENFIELD, scenario="greenfield", **extra):
    response = client.post(
        "/api/workflows", json={"requirement": text, "scenario": scenario, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client, workflow_id, gate, approved=True, comment="ok"):
    return client.post(
        f"/api/workflows/{workflow_id}/approval",
        json={"gate": gate, "approved": approved, "approver": "Reviewer", "comment": comment},
    )


def test_full_workflow_through_the_api(api_client):
    state = _start(api_client)
    wid = state["id"]
    assert state["status"] == "awaiting_implementation_approval"

    graph = api_client.get(f"/api/workflows/{wid}/graph").json()
    assert graph["layers"][1] == ["T2", "T3"] or sorted(graph["layers"][1]) == ["T2", "T3"]
    assert "flowchart TD" in graph["mermaid"]

    assert (
        _approve(api_client, wid, "implementation").json()["status"] == "awaiting_release_approval"
    )
    assert api_client.get(f"/api/workflows/{wid}/summary").status_code == 200
    assert _approve(api_client, wid, "release").json()["status"] == "release_ready"

    assert api_client.get(f"/api/workflows/{wid}").json()["status"] == "release_ready"
    assert api_client.get(f"/api/workflows/{wid}/audit").json()["integrity"]["valid"] is True
    assert "src/shortcode.py" in api_client.get(f"/api/workflows/{wid}/artifacts").json()["files"]
    assert [w["id"] for w in api_client.get("/api/workflows").json()] == [wid]


def test_metrics_route_is_not_shadowed_by_workflow_id_route(api_client):
    _start(api_client)
    response = api_client.get("/api/workflows/metrics")
    assert response.status_code == 200
    assert response.json()["total_workflows"] == 1


def test_error_mapping(api_client):
    assert api_client.get("/api/workflows/nope").status_code == 404
    state = _start(api_client)
    assert _approve(api_client, state["id"], "release").status_code == 409
    assert api_client.get(f"/api/workflows/{state['id']}/summary").status_code == 409
    assert (
        api_client.post(
            "/api/workflows", json={"requirement": "short", "scenario": "greenfield"}
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/workflows",
            json={
                "requirement": GREENFIELD,
                "scenario": "greenfield",
                "fault_injection": {"G1": 1},
            },
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            f"/api/workflows/{state['id']}/approval",
            json={"gate": "implementation", "approved": True, "approver": "agent"},
        ).status_code
        == 422
    )


def test_ambiguity_clarification_and_replan_through_the_api(api_client):
    state = _start(api_client, AMBIGUOUS, "ambiguous")
    wid = state["id"]
    assert state["status"] == "awaiting_clarification"
    assert _approve(api_client, wid, "implementation").status_code == 409

    clarified = api_client.post(
        f"/api/workflows/{wid}/clarify", json={"clarified_requirement": CLARIFIED, "author": "PO"}
    )
    assert clarified.json()["status"] == "awaiting_implementation_approval"

    replanned = api_client.post(
        f"/api/workflows/{wid}/replan",
        json={"changed_node": "T2", "reason": "Impact analysis refreshed"},
    )
    assert replanned.status_code == 200
    assert replanned.json()["decisions"][-1]["preserved"] == ["T1", "T3"]


def test_rollback_is_visible_through_the_api(api_client):
    state = _start(api_client, fault_injection={"T5": 99})
    result = _approve(api_client, state["id"], "implementation").json()
    assert result["status"] == "safe_stopped_rolled_back"
    metrics = api_client.get("/api/workflows/metrics").json()
    assert metrics["rollbacks"] == 1 and metrics["success_rate_pct"] == 0.0
