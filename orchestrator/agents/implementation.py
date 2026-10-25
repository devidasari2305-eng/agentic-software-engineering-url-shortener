from orchestrator import templates
from orchestrator.agents.base import NodeContext
from orchestrator.errors import PolicyViolation


def run(ctx: NodeContext) -> dict:
    analysis = ctx.output("T1")
    files = templates.render(
        analysis["capabilities"], ctx.requirement, analysis["acceptance_criteria"]
    )

    scan = ctx.policy.scan_code(files)
    blocks = ctx.policy.blocking(scan)
    if blocks:
        raise PolicyViolation(blocks[0].rule_id, "; ".join(f"{b.name}: {b.reason}" for b in blocks))

    written = [ctx.workspace.write(path, content) for path, content in files.items()]
    return {
        "generator": "template-catalog",
        "capabilities": analysis["capabilities"],
        "files": written,
        "policy_scan": [r.to_dict() for r in scan],
        "artifacts": written,
    }
