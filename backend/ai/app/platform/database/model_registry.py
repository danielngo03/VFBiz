from importlib import import_module


def load_models() -> None:
    """Load model modules once so SQLAlchemy and Alembic share one metadata graph."""
    for module_name in (
        "app.modules.datasets.infrastructure.models",
        "app.modules.evaluation.infrastructure.models",
        "app.modules.governance.infrastructure.models",
        "app.modules.knowledge.infrastructure.ingestion_models",
        "app.modules.knowledge.infrastructure.models",
        "app.platform.audit.models",
        "app.platform.checkpoints.models",
    ):
        import_module(module_name)
