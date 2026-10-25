from orchestrator.agents.base import NodeContext


def run(ctx: NodeContext) -> dict:
    analysis = ctx.output("T1")
    architecture = ctx.output("T2")
    implementation = ctx.output("T4")
    impact = architecture.get("impact") or {}

    lines = [
        "# Change notes",
        "",
        f"**Requirement (v{ctx.version}):** {ctx.requirement}",
        "",
        "## Capabilities",
        *[f"- {c}" for c in analysis["capabilities"]],
        "",
        "## Acceptance criteria",
        *[f"- {c}" for c in analysis["acceptance_criteria"]],
        "",
        "## Impacted modules" if impact else "## Proposed components",
    ]
    if impact:
        lines += [
            f"- `{m['module']}` ({', '.join(m['matched_symbols'][:3])})"
            for m in impact["direct_modules"]
        ]
        lines += [
            f"- `{m['module']}` (depends on `{m['depends_on']}`)"
            for m in impact["dependent_modules"]
        ]
        lines += ["", "## Routes affected", *[f"- {r}" for r in impact["routes_affected"]]]
    else:
        lines += [f"- {c}" for c in architecture["components"]]
    lines += [
        "",
        "## Generated files",
        *[f"- `{f}`" for f in implementation["files"]],
        "",
        "## Rollback",
        architecture["rollback_strategy"],
        "",
    ]
    path = ctx.workspace.write("docs/change-notes.md", "\n".join(lines))
    return {"document": path, "artifacts": [path]}
