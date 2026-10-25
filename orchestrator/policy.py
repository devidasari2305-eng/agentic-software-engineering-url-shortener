"""Policy engine: security, compliance and change-control guardrails.

Every rule is evaluated and recorded (allow / require_approval / block), so the audit trail
shows what was checked, not only what failed.
"""

import re
from dataclasses import asdict, dataclass

_SECRET = re.compile(
    r"(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|password\s*[:=]\s*\S+)",
    re.IGNORECASE,
)

# (rule id, name, pattern) -> any match blocks the workflow (agents may not do this at all).
_REQUIREMENT_BLOCKS = [
    (
        "POL-001",
        "No autonomous production changes",
        re.compile(r"\b(deploy|push|promote)\b.{0,60}\bprod(uction)?\b", re.IGNORECASE),
    ),
    (
        "POL-002",
        "Governance controls cannot be bypassed",
        re.compile(
            r"\b(bypass|skip|disable|remove)\b.{0,20}\b(approval|audit|authentication|guardrails?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "POL-003",
        "No destructive data operations",
        re.compile(r"\b(drop\s+table|truncate|delete\s+all|wipe)\b", re.IGNORECASE),
    ),
    ("POL-004", "No secrets in requirements", _SECRET),
]

# Matches here do not block, but require a human to acknowledge the risk with a comment.
_REQUIREMENT_APPROVALS = [
    (
        "POL-010",
        "Schema or data change",
        re.compile(
            r"\b(migration|schema|alter\s+table|new\s+column|breaking\s+change)\b", re.IGNORECASE
        ),
    ),
    (
        "POL-012",
        "Sensitive data or access control",
        re.compile(r"\b(auth\w*|pii|personal\s+data|encrypt\w*|credential\w*)\b", re.IGNORECASE),
    ),
]

_CODE_BLOCKS = [
    ("POL-020", "No dynamic code execution", re.compile(r"\b(eval|exec)\s*\(")),
    ("POL-021", "No process execution", re.compile(r"\b(os\.system|subprocess\.|popen\s*\()")),
    ("POL-022", "No unsafe deserialization", re.compile(r"pickle\.loads?|yaml\.load\s*\(")),
    ("POL-023", "No hard-coded secrets", _SECRET),
    ("POL-024", "No outbound network access", re.compile(r"^\s*(import|from)\s+(socket|requests|urllib|httpx)\b", re.M)),
]  # fmt: skip


@dataclass
class PolicyResult:
    rule_id: str
    name: str
    decision: str  # allow | require_approval | block
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class PolicyEngine:
    def evaluate_requirement(self, requirement: str, risk_level: str) -> list[PolicyResult]:
        results: list[PolicyResult] = []
        for rule_id, name, pattern in _REQUIREMENT_BLOCKS:
            match = pattern.search(requirement)
            results.append(
                PolicyResult(rule_id, name, "block", f"Matched '{match.group(0)}'")
                if match
                else PolicyResult(rule_id, name, "allow", "No match")
            )
        for rule_id, name, pattern in _REQUIREMENT_APPROVALS:
            match = pattern.search(requirement)
            results.append(
                PolicyResult(rule_id, name, "require_approval", f"Matched '{match.group(0)}'")
                if match
                else PolicyResult(rule_id, name, "allow", "No match")
            )
        results.append(
            PolicyResult("POL-011", "High-risk change control", "require_approval", "Risk is high")
            if risk_level == "high"
            else PolicyResult(
                "POL-011", "High-risk change control", "allow", f"Risk is {risk_level}"
            )
        )
        return results

    def scan_code(self, files: dict[str, str]) -> list[PolicyResult]:
        results: list[PolicyResult] = []
        for rule_id, name, pattern in _CODE_BLOCKS:
            offenders = sorted(path for path, content in files.items() if pattern.search(content))
            results.append(
                PolicyResult(rule_id, name, "block", f"Found in {', '.join(offenders)}")
                if offenders
                else PolicyResult(rule_id, name, "allow", f"{len(files)} files scanned")
            )
        return results

    @staticmethod
    def blocking(results: list[PolicyResult]) -> list[PolicyResult]:
        return [r for r in results if r.decision == "block"]

    @staticmethod
    def approvals_required(results: list[PolicyResult]) -> list[PolicyResult]:
        return [r for r in results if r.decision == "require_approval"]
