from pathlib import Path

from orchestrator.codebase import CodebaseAnalyzer

ROOT = Path(__file__).resolve().parents[1]


def test_scan_builds_module_graph_with_imports():
    modules = CodebaseAnalyzer(ROOT).scan()
    assert "app.services.url_service" in modules
    assert "app.models.url" in modules["app.services.url_service"].imports


def test_routes_include_router_prefix():
    modules = CodebaseAnalyzer(ROOT).scan()
    routes = modules["app.api.urls"].routes
    assert "POST /api/urls" in routes
    assert "GET /api/urls/{code}/analytics" in routes
    assert "GET /{code}" in routes


def test_expiration_impact_is_derived_from_real_code():
    impact = CodebaseAnalyzer(ROOT).impact(["expir"])
    direct = {m["module"] for m in impact["direct_modules"]}
    assert {"app.models.url", "app.schemas.url", "app.services.url_service"} <= direct
    assert "app.main" in {m["module"] for m in impact["dependent_modules"]}
    assert any("app.services.url_service -> app.models.url" in f for f in impact["data_flows"])
    assert "tests/test_urls.py" in impact["tests_to_review"]


def test_unknown_keyword_has_no_impact_and_missing_repo_is_safe(tmp_path):
    assert CodebaseAnalyzer(ROOT).impact(["zzzunknown"])["direct_modules"] == []
    assert CodebaseAnalyzer(tmp_path).impact(["expir"])["modules_scanned"] == 0
