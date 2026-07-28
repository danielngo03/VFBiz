from __future__ import annotations

import ast
from pathlib import Path

APPLICATION_ROOT = (
    Path(__file__).resolve().parents[3] / "app" / "modules" / "datasets" / "application"
)
FORBIDDEN_TOP_LEVEL_IMPORTS = {
    "argparse",
    "csv",
    "google",
    "httpx",
    "os",
    "pathlib",
    "redis",
    "shutil",
    "sqlalchemy",
    "subprocess",
    "tempfile",
    "zipfile",
}
FORBIDDEN_DATASET_DEPENDENCIES = (
    "app.modules.datasets.infrastructure",
    "app.modules.datasets.presentation",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    return tuple(imported)


def test_dataset_application_is_free_of_runtime_implementation_dependencies() -> None:
    findings: list[str] = []
    for path in sorted(APPLICATION_ROOT.rglob("*.py")):
        for imported in _imports(path):
            top_level = imported.split(".", 1)[0]
            if top_level in FORBIDDEN_TOP_LEVEL_IMPORTS or imported.startswith(
                FORBIDDEN_DATASET_DEPENDENCIES
            ):
                findings.append(f"{path.relative_to(APPLICATION_ROOT)} imports {imported}")
    assert findings == []


def test_legacy_catch_all_application_modules_are_removed() -> None:
    forbidden = {
        "artifact_inspection.py",
        "exporters.py",
        "local_reconciliation.py",
        "local_scan.py",
        "ports.py",
        "quarantine.py",
        "safe_archive.py",
    }
    assert forbidden.isdisjoint(path.name for path in APPLICATION_ROOT.iterdir())
