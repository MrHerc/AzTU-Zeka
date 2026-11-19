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
    bad = {str(f.relative_to(ZEKA)): m for f in ZEKA.glob("modules/*/domain.py") for m in _imports(f)
           if m == "sqlite3" or m.startswith(FORBIDDEN_IN_DOMAIN)}
    assert not bad, bad


def test_sql_lives_only_in_repo_files():
    """SPEC.md: a module's SQL is in its repo.py (Checkpoint C, R10)."""
    sql = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ")
    bad = [str(f.relative_to(ZEKA)) for f in ZEKA.glob("modules/*/*.py")
           if f.name in ("service.py", "routes.py", "domain.py") and any(k in f.read_text(encoding="utf-8") for k in sql)]
    assert bad == []


def test_resolver_sees_relative_imports():
    # guards the check itself: legacy/common.py imports the web layer relatively
    assert "zeka.core.web" in _imports(ZEKA / "legacy" / "common.py")
