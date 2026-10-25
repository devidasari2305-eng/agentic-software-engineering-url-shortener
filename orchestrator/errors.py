"""Exception taxonomy.

Retryable failures are plain ``Exception`` subclasses. Anything derived from
``NonRetryableError`` is never retried: retrying a policy violation or a failed
release check cannot make it succeed and would only waste agent budget.
"""


class OrchestratorError(Exception):
    """Base class for errors raised to API callers."""


class WorkflowNotFound(OrchestratorError):
    pass


class InvalidTransition(OrchestratorError):
    """The requested action is not allowed in the workflow's current state (HTTP 409)."""


class ApprovalError(OrchestratorError):
    """The approval itself is not acceptable, e.g. a missing mandatory comment (HTTP 422)."""


class InvalidRequest(OrchestratorError):
    pass


class NonRetryableError(Exception):
    pass


class PolicyViolation(NonRetryableError):
    def __init__(self, rule_id: str, message: str):
        super().__init__(f"[{rule_id}] {message}")
        self.rule_id = rule_id


class ValidationFailure(NonRetryableError):
    pass


class QualityGateFailure(Exception):
    """Tests or other quality checks failed. Retryable: the cause may be transient."""


class InjectedFault(Exception):
    """Deliberate failure used to demonstrate retry, fallback and rollback."""
