from orchestrator.agents.base import NodeContext, to_json
from orchestrator.catalog import CAPABILITIES, impact_keywords


def run(ctx: NodeContext) -> dict:
    analysis = ctx.output("T1")
    capabilities = analysis["capabilities"]
    components = [c for name in capabilities for c in CAPABILITIES[name]["components"]]

    if ctx.scenario == "greenfield":
        mode = "greenfield"
        impact = None
        schema_change = True
        notes = ["New system: no existing modules to analyse; components proposed from the catalog"]
    else:
        mode = "brownfield"
        impact = ctx.analyzer.impact(impact_keywords(capabilities, ctx.requirement))
        existing = {s for m in impact["direct_modules"] for s in m["matched_symbols"]}
        schema_change = "expires_at" not in existing if "expiration" in capabilities else False
        notes = [
            f"Scanned {impact['modules_scanned']} modules with ast",
            f"{len(impact['direct_modules'])} directly and "
            f"{len(impact['dependent_modules'])} transitively impacted",
        ]
        if "expiration" in capabilities and not schema_change:
            notes.append("expires_at already exists in the data model: no schema migration needed")

    result = {
        "mode": mode,
        "capabilities": capabilities,
        "components": components,
        "impact": impact,
        "schema_change": schema_change,
        "decisions": [
            "Modular monolith: API, service and persistence stay separate layers",
            "Generated code is isolated in a per-workflow workspace, never in the live repo",
            "Backward compatibility is preserved: new behaviour is opt-in",
        ],
        "rollback_strategy": "Restore the pre-implementation checkpoint and reset downstream nodes",
        "notes": notes,
    }
    path = ctx.workspace.write("analysis/impact-analysis.json", to_json(result))
    return {**result, "artifacts": [path]}
