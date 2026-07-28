from importlib import import_module
from types import ModuleType

import pytest


class _ScalarResult:
    def scalar_one(self) -> bool:
        return True


class _GovernedRowsConnection:
    def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult()


def migration() -> ModuleType:
    return import_module("migrations.versions.20260728_0016_dataset_registry")


def test_downgrade_stops_before_destructive_ddl_when_dataset_records_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = migration()
    destructive_calls: list[str] = []

    def record_destructive(*_args: object, **_kwargs: object) -> None:
        destructive_calls.append("destructive")

    monkeypatch.setattr(revision.op, "get_bind", lambda: _GovernedRowsConnection())
    monkeypatch.setattr(revision.op, "drop_table", record_destructive)

    with pytest.raises(RuntimeError, match="governed dataset records exist"):
        revision.downgrade()

    assert destructive_calls == []
