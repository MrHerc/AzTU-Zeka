"""Layer rules of backend/zeka (SPEC.md, Project Structure).

core/   platform: may not import legacy/ or modules/.
modules/<id>/domain.py   rules only: no I/O, no HTTP, no database.
"""
import ast
from pathlib import Path

ZEKA = Path(__file__).resolve().parents[2] / "backend" / "zeka"
FORBIDDEN_IN_DOMAIN = ("sqlite3", "zeka.core.web", "zeka.core.db", "zeka.legacy", "http", "urllib", "socket")


def _imports(path: Path) -> list[str]:
    """Absolute module names a file imports; relative imports are resolved against its package."""
    pkg = path.relative_to(ZEKA.parent).with_suffix("").parts[:-1]
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = list(pkg[: len(pkg) - node.level + 1]) if node.level else []
            mod = ".".join(base + ([node.module] if node.module else []))
            out += [mod] + [f"{mod}.{a.name}" for a in node.names]
    return out


def test_core_does_not_import_legacy_or_modules():
    bad = {str(f.relative_to(ZEKA)): m for f in (ZEKA / "core").rglob("*.py") for m in _imports(f)
           if m.startswith(("zeka.legacy", "zeka.modules"))}
    assert not bad, bad


def test_domain_files_have_no_io():
    """Rules and the timetable solver (Task 48) are pure: no database, no network, no clock (the solver takes one)."""
    solver = ZEKA / "modules" / "timetable" / "solver.py"
    bad = {str(f.relative_to(ZEKA)): m for f in [*ZEKA.glob("modules/*/domain.py"), solver] for m in _imports(f)
           if m == "sqlite3" or m.startswith(FORBIDDEN_IN_DOMAIN)}
    clock = [m for m in _imports(solver) if m.split(".")[0] in ("time", "datetime", "os") or m.endswith((".repo", ".service"))]
    if clock:
        bad["solver"] = ", ".join(clock)
    assert not bad, bad


def test_sql_lives_only_in_repo_files():
    """SPEC.md: a module's SQL is in its repo.py (Checkpoint C, R10); the timetable builder's service too (Task 48)."""
    sql = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ")
    bad = [str(f.relative_to(ZEKA)) for f in ZEKA.glob("modules/*/*.py")
           if f.name in ("service.py", "routes.py", "domain.py", "builder.py") and any(k in f.read_text(encoding="utf-8") for k in sql)]
    assert bad == []


def test_resolver_sees_relative_imports():
    # guards the check itself: legacy/common.py imports the web layer relatively
    assert "zeka.core.web" in _imports(ZEKA / "legacy" / "common.py")


def test_no_module_imports_another_module_s_repo():
    """SPEC.md: modules call each other's service, never their repo (Checkpoint E, AR-E8)."""
    bad = {}
    for f in ZEKA.rglob("*.py"):
        rel = f.relative_to(ZEKA).parts
        own = rel[1] if rel[0] == "modules" else None
        for m in _imports(f):
            p = m.split(".")
            if len(p) >= 4 and p[:2] == ["zeka", "modules"] and p[3] == "repo" and p[2] != own:
                bad.setdefault(str(f.relative_to(ZEKA)), set()).add(m)
    assert not bad, bad
