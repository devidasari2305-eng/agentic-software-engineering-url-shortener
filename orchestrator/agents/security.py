from orchestrator.agents.base import NodeContext, to_json
from orchestrator.errors import PolicyViolation


def run(ctx: NodeContext) -> dict:
    analysis = ctx.output("T1")
    results = ctx.policy.evaluate_requirement(ctx.requirement, analysis["risk_level"])
    payload = [r.to_dict() for r in results]
    path = ctx.workspace.write("analysis/policy-evaluation.json", to_json(payload))

    blocks = ctx.policy.blocking(results)
    if blocks:
        raise PolicyViolation(blocks[0].rule_id, "; ".join(f"{b.name}: {b.reason}" for b in blocks))

    approvals = ctx.policy.approvals_required(results)
    return {
        "policy_results": payload,
        "approval_required_rules": [r.rule_id for r in approvals],
        "checks": ["requirement policy rules", "autonomy boundary", "change control"],
        "artifacts": [path],
    }
