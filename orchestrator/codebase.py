"""Static codebase reasoning (brownfield): scan the real repository with ``ast``.

Builds a module/import graph, extracts symbols, names used and HTTP routes, then answers
"which modules, APIs and data flows does this change touch?" for a set of keywords.
"""

import ast
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

_HTTP_METHODS = {"get", "post", "put", "delete", "patch"}


@dataclass
class ModuleInfo:
    name: str
    path: str
    imports: set[str] = field(default_factory=set)
    symbols: set[str] = field(default_factory=set)
    used_names: set[str] = field(default_factory=set)
    routes: list[str] = field(default_factory=list)


class CodebaseAnalyzer:
    def __init__(self, repo_root: Path, package: str = "app", tests_dir: str = "tests"):
        self.repo_root = Path(repo_root)
        self.package = package
        self.tests_dir = tests_dir

    def scan(self) -> dict[str, ModuleInfo]:
        base = self.repo_root / self.package
        modules: dict[str, ModuleInfo] = {}
        if not base.is_dir():
            return modules
        raw_imports: dict[str, set[str]] = {}
        for path in sorted(base.rglob("*.py")):
            relative = path.relative_to(self.repo_root).with_suffix("")
            parts = list(relative.parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            name = ".".join(parts)
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            info = ModuleInfo(name=name, path=path.relative_to(self.repo_root).as_posix())
            candidates: set[str] = set()
            prefixes = self._router_prefixes(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                    info.symbols.add(node.name)
                    if not isinstance(node, ast.ClassDef):
                        info.routes += self._routes(node, prefixes)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    info.symbols.add(node.target.id)
                elif isinstance(node, ast.Name):
                    info.used_names.add(node.id)
                elif isinstance(node, ast.Attribute):
                    info.used_names.add(node.attr)
                elif isinstance(node, ast.Import):
                    candidates.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    candidates.add(node.module)
                    candidates.update(f"{node.module}.{alias.name}" for alias in node.names)
            raw_imports[name] = candidates
            modules[name] = info
        for name, candidates in raw_imports.items():
            modules[name].imports = {c for c in candidates if c in modules and c != name}
        return modules

    @staticmethod
    def _router_prefixes(tree: ast.AST) -> dict[str, str]:
        """Map router variable names to their APIRouter(prefix=...) value."""
        prefixes: dict[str, str] = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "APIRouter"
            ):
                prefix = next(
                    (
                        kw.value.value
                        for kw in node.value.keywords
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant)
                    ),
                    "",
                )
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        prefixes[target.id] = str(prefix)
        return prefixes

    @staticmethod
    def _routes(
        node: ast.FunctionDef | ast.AsyncFunctionDef, prefixes: dict[str, str]
    ) -> list[str]:
        routes = []
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in _HTTP_METHODS
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                owner = decorator.func.value
                prefix = prefixes.get(owner.id, "") if isinstance(owner, ast.Name) else ""
                path = f"{prefix}{decorator.args[0].value}" or "/"
                routes.append(f"{decorator.func.attr.upper()} {path}")
        return routes

    def impact(self, keywords: list[str]) -> dict:
        modules = self.scan()
        kws = [k.lower() for k in keywords if k]

        direct: dict[str, list[str]] = {}
        for name, info in modules.items():
            haystack = info.symbols | info.used_names | {r.lower() for r in info.routes}
            hits = sorted(s for s in haystack if any(k in s.lower() for k in kws))
            if hits:
                direct[name] = hits

        importers: dict[str, set[str]] = {name: set() for name in modules}
        for name, info in modules.items():
            for imported in info.imports:
                importers[imported].add(name)

        dependents: dict[str, str] = {}
        queue = deque((name, 0) for name in direct)
        while queue:
            current, depth = queue.popleft()
            if depth >= 2:
                continue
            for importer in sorted(importers[current]):
                if importer not in direct and importer not in dependents:
                    dependents[importer] = current
                    queue.append((importer, depth + 1))

        involved = set(direct) | set(dependents)
        return {
            "keywords": kws,
            "modules_scanned": len(modules),
            "direct_modules": [
                {"module": n, "path": modules[n].path, "matched_symbols": hits[:8]}
                for n, hits in sorted(direct.items())
            ],
            "dependent_modules": [
                {"module": n, "path": modules[n].path, "depends_on": via}
                for n, via in sorted(dependents.items())
            ],
            "routes_affected": sorted(route for n in involved for route in modules[n].routes),
            "data_flows": self._flows(modules, involved),
            "tests_to_review": self._tests(kws),
        }

    @staticmethod
    def _flows(modules: dict[str, ModuleInfo], involved: set[str]) -> list[str]:
        flows: list[str] = []

        def walk(path: list[str]) -> None:
            if len(flows) >= 6:
                return
            following = sorted(
                i for i in modules[path[-1]].imports if i in involved and i not in path
            )
            if not following:
                if len(path) > 1:
                    flows.append(" -> ".join(path))
                return
            for nxt in following:
                walk([*path, nxt])

        for name in sorted(involved):
            if modules[name].routes:
                walk([name])
        return flows

    def _tests(self, keywords: list[str]) -> list[str]:
        folder = self.repo_root / self.tests_dir
        if not folder.is_dir():
            return []
        matches = []
        for path in sorted(folder.glob("test_*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if any(k in text for k in keywords):
                matches.append(path.relative_to(self.repo_root).as_posix())
        return matches
