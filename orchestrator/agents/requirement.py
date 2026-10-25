from orchestrator.agents.base import NodeContext, to_json


def _finish(ctx: NodeContext, analysis, source: str) -> dict:
    data = analysis.model_dump()
    path = ctx.workspace.write("analysis/requirements.json", to_json(data))
    return {**data, "provider": source, "artifacts": [path]}


def run(ctx: NodeContext) -> dict:
    analysis = ctx.provider.analyze_requirement(ctx.requirement, ctx.scenario)
    return _finish(ctx, analysis, ctx.provider.name)


def run_fallback(ctx: NodeContext) -> dict:
    analysis = ctx.fallback_provider.analyze_requirement(ctx.requirement, ctx.scenario)
    return _finish(ctx, analysis, f"{ctx.fallback_provider.name} (fallback)")
