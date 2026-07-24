import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
MODULE_ROOT = APP_ROOT / "modules"
APPROVED_MODULES = {
    "assistant",
    "evaluation",
    "governance",
    "inference",
    "knowledge",
    "tooling",
}


def test_only_approved_ai_capabilities_are_top_level_modules() -> None:
    actual = {
        path.name
        for path in MODULE_ROOT.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    assert actual == APPROVED_MODULES


def test_domain_packages_do_not_import_framework_or_orm() -> None:
    forbidden = {"fastapi", "sqlalchemy", "redis", "httpx", "pgvector"}
    violations: list[str] = []
    for file in MODULE_ROOT.glob("*/domain/**/*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in forbidden:
                    violations.append(f"{file.relative_to(APP_ROOT)} imports {name}")
    assert violations == []
