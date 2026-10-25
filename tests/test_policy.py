import pytest

from orchestrator.policy import PolicyEngine

policy = PolicyEngine()


def _decisions(results):
    return {r.rule_id: r.decision for r in results}


@pytest.mark.parametrize(
    "text",
    [
        "Deploy the new cache directly to production",
        "Bypass approval for hotfixes",
        "Drop table short_urls to reset data",
        "Use password: hunter2 for the admin account",
    ],
)
def test_forbidden_requirements_are_blocked(text):
    assert policy.blocking(policy.evaluate_requirement(text, "medium"))


def test_schema_change_requires_human_acknowledgement():
    results = policy.evaluate_requirement("Add a database migration for a new column", "medium")
    assert _decisions(results)["POL-010"] == "require_approval"
    assert not policy.blocking(results)


def test_high_risk_requires_approval():
    results = policy.evaluate_requirement("Add optional expiration", "high")
    assert _decisions(results)["POL-011"] == "require_approval"


def test_benign_requirement_is_fully_allowed_and_every_rule_is_recorded():
    results = policy.evaluate_requirement("Add optional expiration to short URLs", "medium")
    assert {r.decision for r in results} == {"allow"}
    assert len(results) >= 7


@pytest.mark.parametrize(
    "code",
    [
        "result = eval(user_input)",
        "import os\nos.system('rm -rf /')",
        "import subprocess\nsubprocess.run(['ls'])",
        "import pickle\npickle.loads(blob)",
        "token = 'AKIAABCDEFGHIJKLMNOP'",
        "import socket\n",
    ],
)
def test_dangerous_generated_code_is_blocked(code):
    assert policy.blocking(policy.scan_code({"src/bad.py": code}))


def test_safe_generated_code_passes():
    results = policy.scan_code({"src/ok.py": "def add(a, b):\n    return a + b\n"})
    assert not policy.blocking(results)
