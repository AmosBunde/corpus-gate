"""Registering is provenance-complete; rollback is a pointer move."""

import json
from pathlib import Path

import pytest

from corpusgate.finetune import registry


def make_candidate(root: Path, dry_run: bool = False) -> Path:
    candidate = root / "candidate"
    (candidate / "adapter").mkdir(parents=True)
    (candidate / "pairs.jsonl").write_text('{"pair_id": "pair-0000"}\n')
    (candidate / "decontam_report.md").write_text("# report\n")
    (candidate / "adapter" / "training_run.json").write_text(
        json.dumps({"base_model": "tiny", "dry_run": dry_run, "steps": 2})
    )
    return candidate


def test_register_moves_and_hashes(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    entry = registry.register("v1", candidate, root=tmp_path)
    assert not candidate.exists()
    assert (tmp_path / "v1" / "pairs.jsonl").exists()
    assert len(entry["pairs_manifest_sha256"]) == 64
    index = registry.load_index(tmp_path)
    assert "v1" in index["versions"] and index["champion_adapter"] is None


def test_register_refuses_incomplete_and_duplicate(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    (candidate / "decontam_report.md").unlink()
    with pytest.raises(FileNotFoundError, match="incomplete"):
        registry.register("v1", candidate, root=tmp_path)
    (candidate / "decontam_report.md").write_text("# report\n")
    registry.register("v1", candidate, root=tmp_path)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("v1", make_candidate(tmp_path), root=tmp_path)


def test_promote_and_rollback_are_pointer_moves(tmp_path: Path) -> None:
    registry.register("v1", make_candidate(tmp_path), root=tmp_path)
    registry.register("v2", make_candidate(tmp_path), root=tmp_path)
    registry.promote("v2", root=tmp_path)
    assert registry.load_index(tmp_path)["champion_adapter"] == "v2"
    before = (tmp_path / "v2" / "pairs.jsonl").read_bytes()
    registry.promote("v1", root=tmp_path)  # rollback
    assert registry.load_index(tmp_path)["champion_adapter"] == "v1"
    assert (tmp_path / "v2" / "pairs.jsonl").read_bytes() == before, "rollback touches nothing"


def test_dry_run_adapters_cannot_be_champion(tmp_path: Path) -> None:
    registry.register("v1", make_candidate(tmp_path, dry_run=True), root=tmp_path)
    with pytest.raises(ValueError, match="dry-run"):
        registry.promote("v1", root=tmp_path)
    with pytest.raises(ValueError, match="unknown version"):
        registry.promote("v9", root=tmp_path)
