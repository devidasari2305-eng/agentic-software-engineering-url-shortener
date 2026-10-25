from orchestrator.agents.base import NodeContext
from orchestrator.errors import ValidationFailure


def _summary(ctx: NodeContext, checks: dict, manifest: dict) -> str:
    t1, t2, t3, t4, t5 = (ctx.output(n) for n in ("T1", "T2", "T3", "T4", "T5"))
    rows = [
        f"| {nid} | {n['name']} | {', '.join(n['depends_on']) or '-'} | {n['status']} |"
        for nid, n in ctx.nodes.items()
    ]
    lines = [
        "# Final engineering summary",
        "",
        "## 1. Plan and rationale",
        f"Requirement (plan v{ctx.version}, {ctx.scenario}): {ctx.requirement}",
        "",
        "| Node | Name | Depends on | Status |",
        "|---|---|---|---|",
        *rows,
        "",
        "Key decisions:",
        *[f"- {d}" for d in t2["decisions"]],
        *[f"- {d['type']}: {d.get('reason', '')}".rstrip(": ") for d in ctx.decisions],
        "",
        "## 2. Artifacts",
        "| File | SHA-256 (first 12) |",
        "|---|---|",
        *[f"| `{path}` | {digest[:12]} |" for path, digest in sorted(manifest.items())],
        "",
        "## 3. Risks, trade-offs and validation",
        *[f"- Risk: {r}" for r in t1["risks"]],
        f"- Tests executed with pytest: {t5['passed']} passed, {t5['failed']} failed",
        f"- Policy rules evaluated: {len(t3['policy_results'])}; "
        f"approval required by: {', '.join(t3['approval_required_rules']) or 'none'}",
        f"- Code policy scan rules evaluated: {len(t4['policy_scan'])}",
        "- Trade-off: template-based generation is deterministic and reviewable but narrower "
        "than a model-driven generator",
        "",
        "Release checks:",
        *[f"- {'PASS' if ok else 'FAIL'}: {name}" for name, ok in checks.items()],
        "",
        "## 4. Reliability evidence",
        f"- Counters: {ctx.counters}",
        *[
            f"- Incident {i['node']}: {i['kind']} (mttr_ms={i.get('mttr_ms')})"
            for i in ctx.incidents
        ],
        "",
        "## 5. Assumptions",
        *[f"- {a}" for a in t1["assumptions"]],
        "",
        "## 6. Limitations",
        "- Generated code lives in an isolated workspace; merging it is a human decision",
        "- Impact analysis is static (ast) and does not trace dynamic dispatch",
        "- Workflow state is durable (SQLite), but execution is single-process",
        "",
    ]
    return "\n".join(lines)


def run(ctx: NodeContext) -> dict:
    t1, t3, t4, t5 = (ctx.output(n) for n in ("T1", "T3", "T4", "T5"))
    ws = ctx.workspace
    checks = {
        "tests_passed": t5.get("passed", 0) > 0 and t5.get("failed", 0) == 0,
        "documentation_present": ws.exists("docs/change-notes.md"),
        "implementation_artifacts_present": bool(t4.get("files"))
        and all(ws.exists(f) for f in t4["files"]),
        "policy_clear": not any(r["decision"] == "block" for r in t3.get("policy_results", [])),
        "ambiguity_resolved": not t1.get("ambiguities"),
        "rollback_checkpoint_defined": ctx.checkpoint is not None,
    }
    path = ws.write("release/engineering-summary.md", _summary(ctx, checks, ws.manifest()))
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ValidationFailure(f"Release readiness checks failed: {', '.join(failed)}")
    return {
        "ready": True,
        "checks": checks,
        "manifest": ws.manifest(),
        "summary_document": path,
        "artifacts": [path],
    }
