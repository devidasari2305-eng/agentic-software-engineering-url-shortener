import json

import httpx
import pytest
from pydantic import ValidationError

from orchestrator.models import RequirementAnalysis, WorkflowRequest
from orchestrator.providers.deterministic import DeterministicProvider
from orchestrator.providers.openai_compatible import OpenAICompatibleProvider
from tests.helpers import GREENFIELD


class FakeResponse:
    def __init__(self, content: str, status: int = 200):
        self._content, self.status = content, status

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _provider():
    return OpenAICompatibleProvider("test-key", "test-model")


def test_openai_provider_validates_model_output(monkeypatch):
    payload = {"normalized_problem": "Add expiry", "capabilities": ["expiration", "bogus"]}
    sent = {}

    def fake_post(url, headers, json, timeout):  # noqa: A002 - mirrors httpx.post signature
        sent.update(url=url, headers=headers, body=json)
        return FakeResponse(__import__("json").dumps(payload))

    monkeypatch.setattr(httpx, "post", fake_post)
    result = _provider().analyze_requirement("Add expiry", "brownfield")
    assert isinstance(result, RequirementAnalysis)
    assert result.capabilities == ["expiration"]  # unknown capabilities are dropped
    assert sent["headers"]["Authorization"] == "Bearer test-key"
    assert sent["body"]["response_format"] == {"type": "json_object"}


def test_openai_provider_rejects_malformed_model_output(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse('{"unexpected": true}'))
    with pytest.raises(ValidationError):
        _provider().analyze_requirement("Add expiry", "brownfield")


def test_provider_outage_falls_back_to_deterministic_analysis(monkeypatch, make_engine):
    def outage(*args, **kwargs):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx, "post", outage)
    engine = make_engine(provider=_provider(), max_retries=1)
    state = engine.start(WorkflowRequest(requirement=GREENFIELD, scenario="greenfield"))
    assert state["status"] == "awaiting_implementation_approval"
    assert state["nodes"]["T1"]["via"] == "fallback"
    assert state["counters"]["retries"] == 1 and state["counters"]["fallbacks"] == 1
    assert "network down" in json.dumps(engine.audit(state["id"])["events"])


def test_numeric_target_removes_ambiguity_but_vague_wording_does_not():
    provider = DeterministicProvider()
    vague = provider.analyze_requirement("Make popular URLs faster for everyone", "ambiguous")
    precise = provider.analyze_requirement("Make redirects faster: p95 under 50 ms", "brownfield")
    assert vague.ambiguities and not precise.ambiguities
    assert "caching" in precise.capabilities


def test_risk_level_is_high_for_schema_changes():
    result = DeterministicProvider().analyze_requirement(
        "Add a database migration for URL tags", "brownfield"
    )
    assert result.risk_level == "high"
