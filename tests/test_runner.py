"""The runner scores any registered variant end to end without a model or network."""

import json
from pathlib import Path

import pytest

from corpusgate.evals import runner, variants


def test_unknown_variant_fails_with_roster() -> None:
    with pytest.raises(KeyError, match="registered variants"):
        variants.get_variant("nonexistent")


def test_echo_refuses_everything() -> None:
    answer = variants.EchoVariant().answer({"id": "q-001"})
    assert answer.refused is True
    assert answer.citations == []


def test_oracle_cites_gold_anchors_and_refuses_refusals() -> None:
    oracle = variants.OracleVariant()
    lookup = oracle.answer(
        {
            "category": "lookup",
            "reference_answer": "A verified figure.",
            "gold_anchors": ["AAPL-10-K-2025-10-31#item-7"],
        }
    )
    assert lookup.refused is False
    assert [c.chunk_id for c in lookup.citations] == ["AAPL-10-K-2025-10-31#item-7"]
    refusal = oracle.answer(
        {"category": "refusal", "reference_answer": "Not in the corpus.", "gold_anchors": []}
    )
    assert refusal.refused is True


def test_full_run_records_every_question(tmp_path: Path) -> None:
    run_dir = runner.run_eval("echo", out_root=tmp_path)
    records = [json.loads(line) for line in (run_dir / "records.jsonl").read_text().splitlines()]
    meta = json.loads((run_dir / "run.json").read_text())
    expected = sum(1 for _ in open("evalset/questions.jsonl"))
    assert len(records) == expected
    assert meta["question_count"] == expected
    assert meta["variant"] == "echo"
    assert all(r["latency_ms"] >= 0 for r in records)
    assert {r["question_id"] for r in records} == {f"q-{i:03d}" for i in range(1, expected + 1)}


def test_smoke_run_selects_exactly_the_slice(tmp_path: Path) -> None:
    run_dir = runner.run_eval("oracle", out_root=tmp_path, smoke_only=True)
    records = [json.loads(line) for line in (run_dir / "records.jsonl").read_text().splitlines()]
    assert len(records) == 10
    assert all(r["smoke"] for r in records)
    categories = {r["category"] for r in records}
    assert categories == {"lookup", "cross_reference", "synthesis", "refusal"}
