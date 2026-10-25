from sqlalchemy import update

from orchestrator.store import AuditRow, WorkflowStore


def _store(tmp_path):
    return WorkflowStore(f"sqlite:///{(tmp_path / 's.db').as_posix()}")


def test_state_round_trip_and_listing(tmp_path):
    store = _store(tmp_path)
    state = {"id": "w1", "status": "running", "version": 1, "created_at": "a", "updated_at": "b"}
    store.save(state)
    assert store.load("w1") == state
    assert store.load("missing") is None
    state["status"] = "release_ready"
    store.save(state)
    assert [s["status"] for s in store.all_states()] == ["release_ready"]


def test_audit_chain_is_valid_and_ordered(tmp_path):
    store = _store(tmp_path)
    for index in range(4):
        store.append_audit("w1", "T1", f"event{index}", {"n": index})
    assert [e["seq"] for e in store.audit("w1")] == [1, 2, 3, 4]
    assert store.verify_chain("w1") == {"valid": True, "events": 4, "broken_at_seq": None}


def test_audit_tampering_is_detected(tmp_path):
    store = _store(tmp_path)
    for index in range(3):
        store.append_audit("w1", None, f"event{index}", {"n": index})
    with store.raw_session() as session:
        session.execute(
            update(AuditRow)
            .where(AuditRow.workflow_id == "w1", AuditRow.seq == 2)
            .values(detail='{"n": 999}')
        )
        session.commit()
    verdict = store.verify_chain("w1")
    assert verdict["valid"] is False
    assert verdict["broken_at_seq"] == 2


def test_chains_are_independent_per_workflow(tmp_path):
    store = _store(tmp_path)
    store.append_audit("a", None, "x", {})
    store.append_audit("b", None, "x", {})
    assert store.verify_chain("a")["valid"] and store.verify_chain("b")["valid"]
