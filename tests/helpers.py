"""Shared test constants and doubles."""

GREENFIELD = "Build a URL shortener API with click analytics and reliable redirects"
BROWNFIELD = "Add optional expiration to the existing URL shortener"
AMBIGUOUS = "Make popular URLs faster"
CLARIFIED = (
    "Cache redirects for URLs with more than 100 clicks per hour for 60 seconds, "
    "targeting p95 redirect latency under 50 ms"
)


class FakeRunner:
    """Fast stand-in for pytest so orchestration tests do not spawn subprocesses."""

    def __init__(self, passed: int = 5, failed: int = 0):
        self.passed, self.failed, self.calls = passed, failed, 0

    def run(self, workspace_root):
        from orchestrator.test_runner import RunResult

        self.calls += 1
        return RunResult(self.passed, self.failed, 0, 0 if not self.failed else 1, "fake run", 1.0)
