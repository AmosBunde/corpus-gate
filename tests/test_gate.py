"""The gate's rule is exact at the edges and promotion is explicit."""

import json
from pathlib import Path

import pytest

from corpusgate.evals import gate

CONFIG = {"gate": {"champion": None, "category_tolerance": 2.0, "require_overall_gain": True}}

SCORES = {
    "champion": {"lookup": 80.0, "cross_reference": 60.0, "synthesis": 55.0, "refusal": 90.0},
    "up": {"lookup": 82.0, "cross_reference": 70.0, "synthesis": 60.0, "refusal": 90.0},
    "at_tolerance": {"lookup": 78.0, "cross_reference": 70.0, "synthesis": 60.0, "refusal": 90.0},
    "beyond_tolerance": {"lookup": 77.9, "cross_reference": 75.0, "synthesis": 60.0,
                         "refusal": 90.0},
    "tie": {"lookup": 80.0, "cross_reference": 60.0, "synthesis": 55.0, "refusal": 90.0},
}


def write_run(root: Path, name: str, by_category: dict) -> Path:
    run_dir = root / name
    run_dir.mkdir(parents=True)
    rows = []
    for category, score in by_category.items():
        for i in range(2):
            rows.append({"question_id": f"{category}-{i}", "category": category,
                         "score": score, "criteria_met": [True], "rationale": "r"})
    (run_dir / "scores.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (run_dir / "run.json").write_text(json.dumps({"variant": name}))
    return run_dir


@pytest.fixture()
def runs(tmp_path: Path) -> dict:
    return {name: write_run(tmp_path, name, scores) for name, scores in SCORES.items()}


def test_bootstrap_promotes_without_champion(runs: dict) -> None:
    result = gate.verdict(runs["up"], None, CONFIG)
    assert result["verdict"] == "promote" and result["champion"] is None


def test_improvement_promotes(runs: dict) -> None:
    result = gate.verdict(runs["up"], runs["champion"], CONFIG)
    assert result["verdict"] == "promote"
    assert result["deltas"]["cross_reference"] == 10.0


def test_drop_exactly_at_tolerance_passes(runs: dict) -> None:
    result = gate.verdict(runs["at_tolerance"], runs["champion"], CONFIG)
    assert result["verdict"] == "promote", result["reasons"]


def test_drop_beyond_tolerance_rejects_with_named_category(runs: dict) -> None:
    result = gate.verdict(runs["beyond_tolerance"], runs["champion"], CONFIG)
    assert result["verdict"] == "reject"
    assert any("lookup drops" in r for r in result["reasons"])


def test_overall_tie_rejects(runs: dict) -> None:
    result = gate.verdict(runs["tie"], runs["champion"], CONFIG)
    assert result["verdict"] == "reject"
    assert any("overall must rise" in r for r in result["reasons"])


def test_promote_run_copies_and_repoints(runs: dict, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "eval.yaml"
    config_path.write_text(
        "gate:\n  champion: null\n  category_tolerance: 2.0\n  require_overall_gain: true\n"
    )
    promoted = gate.promote_run(runs["up"], config_path)
    assert (promoted / "scores.jsonl").exists()
    import yaml
    assert yaml.safe_load(config_path.read_text())["gate"]["champion"] == str(promoted)
