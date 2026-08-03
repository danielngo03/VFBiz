from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.datasets.domain import RegistryInvariantError
from scripts.retire_local_knowledge_candidates import (
    retire_release_ineligible_candidates,
)


def _candidate(
    root: Path,
    *,
    batch: str,
    release_eligible: bool,
    active_retriever_visible: bool = False,
) -> Path:
    path = root / f"candidate/knowledge/profile/pipeline/batches/{batch}"
    chunk = path / "chunks/document/chunk.json"
    chunk.parent.mkdir(parents=True)
    chunk.write_text('{"text":"derived"}\n', encoding="utf-8")
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "batch_id": batch,
                "release_eligible": release_eligible,
                "active_retriever_visible": active_retriever_visible,
                "documents": {"document": {"chunk_count": 1}},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_retirement_moves_only_release_ineligible_candidate_and_keeps_source(
    tmp_path: Path,
) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    trash = tmp_path / "Trash"
    trash.mkdir()
    retired = _candidate(root, batch="retire-me", release_eligible=False)
    retained = _candidate(root, batch="retain-me", release_eligible=True)
    source = root / "quarantine/aa/source.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-source")

    planned = retire_release_ineligible_candidates(
        object_root=root,
        trash_root=trash,
        actor_ref="user:local-project-owner",
        execute=False,
    )
    result = retire_release_ineligible_candidates(
        object_root=root,
        trash_root=trash,
        actor_ref="user:local-project-owner",
        execute=True,
    )

    assert planned["candidate_count"] == 1
    assert result["candidate_count"] == 1
    assert result["chunk_count"] == 1
    assert not retired.exists()
    assert retained.is_dir()
    assert source.read_bytes() == b"%PDF-source"
    recovery = next(trash.glob("VFBiz-candidate-knowledge-*"))
    assert (recovery / "manifest.json").is_file()
    tombstones = tuple((root / "tombstones/candidate-knowledge").glob("*.json"))
    assert len(tombstones) == 1
    assert json.loads(tombstones[0].read_text(encoding="utf-8"))["state"] == "complete"


def test_retirement_rejects_candidate_visible_to_active_retriever(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    trash = tmp_path / "Trash"
    trash.mkdir()
    _candidate(
        root,
        batch="invalid",
        release_eligible=False,
        active_retriever_visible=True,
    )

    with pytest.raises(RegistryInvariantError, match="active retriever"):
        retire_release_ineligible_candidates(
            object_root=root,
            trash_root=trash,
            actor_ref="user:local-project-owner",
            execute=False,
        )


def test_retirement_rejects_symlinked_candidate_content(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    root.mkdir()
    trash = tmp_path / "Trash"
    trash.mkdir()
    candidate = _candidate(root, batch="invalid", release_eligible=False)
    outside = tmp_path / "outside"
    outside.write_text("outside", encoding="utf-8")
    (candidate / "linked").symlink_to(outside)

    with pytest.raises(RegistryInvariantError, match="symlink"):
        retire_release_ineligible_candidates(
            object_root=root,
            trash_root=trash,
            actor_ref="user:local-project-owner",
            execute=False,
        )
