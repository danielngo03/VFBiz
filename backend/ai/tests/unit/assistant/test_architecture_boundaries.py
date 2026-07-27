import ast
from pathlib import Path


def test_domain_and_application_do_not_depend_on_graph_or_infrastructure() -> None:
    assistant = Path(__file__).parents[4] / "app/modules/assistant"
    forbidden = (
        "app.modules.assistant.graph",
        "app.modules.assistant.infrastructure",
        "langgraph",
        "fastapi",
        "sqlalchemy",
        "redis",
        "httpx",
    )
    violations: list[str] = []
    for layer in ("domain", "application"):
        for file in (assistant / layer).rglob("*.py"):
            tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            for node in ast.walk(tree):
                module = None
                if isinstance(node, ast.ImportFrom):
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden):
                            violations.append(
                                f"{file}:{getattr(node, 'lineno', 0)}:{alias.name}"
                            )
                if module is not None and module.startswith(forbidden):
                    violations.append(
                        f"{file}:{getattr(node, 'lineno', 0)}:{module}"
                    )
    assert violations == []
