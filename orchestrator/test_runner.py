"""Runs the generated test-suite with a real pytest subprocess inside the workflow workspace."""

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    passed: int
    failed: int
    errors: int
    returncode: int
    output: str
    duration_ms: float


class PytestRunner:
    def __init__(self, timeout_seconds: int = 120):
        self.timeout = timeout_seconds

    def run(self, workspace_root: Path) -> RunResult:
        env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header"],
                cwd=str(workspace_root),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
            )
            output = completed.stdout + completed.stderr
            code = completed.returncode
        except subprocess.TimeoutExpired:
            output = f"pytest timed out after {self.timeout}s"
            code = -1
        duration = round((time.perf_counter() - started) * 1000, 2)

        def count(label: str) -> int:
            match = re.search(rf"(\d+) {label}", output)
            return int(match.group(1)) if match else 0

        return RunResult(count("passed"), count("failed"), count("error"), code, output, duration)
