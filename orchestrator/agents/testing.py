from orchestrator.agents.base import NodeContext
from orchestrator.errors import QualityGateFailure


def run(ctx: NodeContext) -> dict:
    result = ctx.test_runner.run(ctx.workspace.root)
    tail = "\n".join(result.output.strip().splitlines()[-30:])
    report = ctx.workspace.write(
        "reports/test-report.txt",
        f"passed={result.passed} failed={result.failed} errors={result.errors} "
        f"returncode={result.returncode}\n\n{tail}\n",
    )
    if result.returncode != 0 or result.failed or result.errors or result.passed == 0:
        raise QualityGateFailure(
            f"Generated tests did not pass (passed={result.passed}, failed={result.failed}, "
            f"errors={result.errors}, returncode={result.returncode})"
        )
    return {
        "passed": result.passed,
        "failed": result.failed,
        "duration_ms": result.duration_ms,
        "report": report,
        "artifacts": [report],
    }
