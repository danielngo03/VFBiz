import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
MODULE_ROOT = APP_ROOT / "modules"
APPROVED_MODULES = {
    "assistant",
    "datasets",
    "evaluation",
    "governance",
    "inference",
    "knowledge",
}
AI_ROOT = APP_ROOT.parent
DATASET_APPLICATION_FORBIDDEN_IMPORTS = {
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
DATASET_APPLICATION_FORBIDDEN_PREFIXES = (
    "app.modules.datasets.infrastructure",
    "app.modules.datasets.presentation",
)
INTERNAL_LAYER_ALIASES = {"application", "domain", "infrastructure", "presentation"}


def _normalized_import(*, module: str | None, level: int, owner_module: str) -> str:
    if level == 0:
        return module or ""
    owner_parts = owner_module.split(".")
    keep = len(owner_parts) - (level - 1)
    base = owner_parts[: max(keep, 0)]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _is_cross_context_deep_import(name: str, owner: str) -> bool:
    parts = name.split(".")
    return len(parts) > 3 and parts[:2] == ["app", "modules"] and parts[2] != owner


def _owner_module(file: Path) -> str:
    relative_parent = file.parent.relative_to(APP_ROOT)
    suffix = ".".join(relative_parent.parts)
    return f"app.{suffix}" if suffix else "app"


def _import_names(tree: ast.AST, *, owner_module: str) -> tuple[str, ...]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _normalized_import(
                module=node.module,
                level=node.level,
                owner_module=owner_module,
            )
            imports.append(base)
            imports.extend(
                f"{base}.{alias.name}"
                for alias in node.names
                if alias.name in INTERNAL_LAYER_ALIASES or alias.name == "*"
            )
    return tuple(imports)


def _imports(file: Path) -> tuple[str, ...]:
    tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    return _import_names(tree, owner_module=_owner_module(file))


def test_from_import_aliases_are_expanded_for_boundary_checks() -> None:
    absolute = ast.parse("from app.modules.datasets import infrastructure")
    relative = ast.parse("from .. import infrastructure")
    cross_context = ast.parse("from app.modules.evaluation import domain")

    assert "app.modules.datasets.infrastructure" in _import_names(
        absolute, owner_module="app.modules.datasets.application"
    )
    assert "app.modules.datasets.infrastructure" in _import_names(
        relative, owner_module="app.modules.datasets.application"
    )
    assert "app.modules.evaluation.domain" in _import_names(
        cross_context, owner_module="app.modules.datasets.application"
    )


def test_relative_imports_are_resolved_before_boundary_checks() -> None:
    assert (
        _normalized_import(
            module="infrastructure", level=2, owner_module="app.modules.datasets.application"
        )
        == "app.modules.datasets.infrastructure"
    )
    assert (
        _normalized_import(
            module="application", level=2, owner_module="app.modules.datasets.domain"
        )
        == "app.modules.datasets.application"
    )


def test_cross_context_public_facade_is_allowed_but_deep_import_is_rejected() -> None:
    assert not _is_cross_context_deep_import("app.modules.evaluation", "datasets")
    assert _is_cross_context_deep_import("app.modules.evaluation.domain.run", "datasets")


def test_dataset_inspection_script_uses_the_presentation_worker_facade() -> None:
    source = (AI_ROOT / "scripts" / "inspect_datasets.py").read_text(encoding="utf-8")
    assert "from app.modules.datasets.presentation.workers import scan_local_downloads" in source


def test_only_approved_ai_capabilities_are_top_level_modules() -> None:
    actual = {
        path.name for path in MODULE_ROOT.iterdir() if path.is_dir() and path.name != "__pycache__"
    }
    assert actual == APPROVED_MODULES


def test_domain_packages_do_not_import_framework_or_orm() -> None:
    forbidden = {"fastapi", "sqlalchemy", "redis", "httpx", "pgvector"}
    violations: list[str] = []
    for file in MODULE_ROOT.glob("*/domain/**/*.py"):
        for name in _imports(file):
            if name.split(".")[0] in forbidden:
                violations.append(f"{file.relative_to(APP_ROOT)} imports {name}")
    assert violations == []


def test_knowledge_and_inference_do_not_depend_on_assistant() -> None:
    violations: list[str] = []
    for owner in ("knowledge", "inference"):
        for file in (MODULE_ROOT / owner).glob("**/*.py"):
            if "__pycache__" in file.parts:
                continue
            for name in _imports(file):
                if name.startswith("app.modules.assistant"):
                    violations.append(f"{file.relative_to(APP_ROOT)} imports {name}")
    assert violations == []


def test_dataset_domain_and_application_do_not_import_other_ai_modules() -> None:
    violations: list[str] = []
    for owner in ("domain", "application"):
        for file in (MODULE_ROOT / "datasets" / owner).glob("**/*.py"):
            for name in _imports(file):
                if _is_cross_context_deep_import(name, "datasets"):
                    violations.append(f"{file.relative_to(APP_ROOT)} imports {name}")
    assert violations == []


def test_dataset_application_uses_ports_instead_of_runtime_implementations() -> None:
    violations: list[str] = []
    application_root = MODULE_ROOT / "datasets" / "application"
    for file in application_root.glob("**/*.py"):
        for name in _imports(file):
            if name.split(".", maxsplit=1)[0] in DATASET_APPLICATION_FORBIDDEN_IMPORTS:
                violations.append(f"{file.relative_to(APP_ROOT)} imports {name}")
            elif name.startswith(DATASET_APPLICATION_FORBIDDEN_PREFIXES):
                violations.append(f"{file.relative_to(APP_ROOT)} imports {name}")
    assert violations == []


def test_dataset_domain_does_not_depend_on_outer_layers() -> None:
    violations: list[str] = []
    domain_root = MODULE_ROOT / "datasets" / "domain"
    forbidden = (
        "app.modules.datasets.application",
        "app.modules.datasets.infrastructure",
        "app.modules.datasets.presentation",
    )
    for file in domain_root.glob("**/*.py"):
        for name in _imports(file):
            if name.startswith(forbidden) or _is_cross_context_deep_import(name, "datasets"):
                violations.append(f"{file.relative_to(APP_ROOT)} imports {name}")
    assert violations == []


def test_dataset_application_legacy_catch_all_modules_stay_removed() -> None:
    application_root = MODULE_ROOT / "datasets" / "application"
    legacy = {
        "artifact_inspection.py",
        "exporters.py",
        "golden_smoke.py",
        "local_reconciliation.py",
        "local_scan.py",
        "ports.py",
        "quality.py",
        "quarantine.py",
        "safe_archive.py",
    }
    assert legacy.isdisjoint(path.name for path in application_root.iterdir())
