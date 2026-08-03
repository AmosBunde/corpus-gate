"""Retrieval metrics are mechanical, prefix-matched, and bracketed by the built-ins."""

import json
from pathlib import Path

import pytest

from corpusgate.evals import judge, metrics, runner, scoreboard, smoke


def test_anchor_prefix_matching() -> None:
    assert metrics.anchor_of("AAPL-10-K-2025-10-31#item-7:14") == "AAPL-10-K-2025-10-31#item-7"
    assert metrics.anchor_of("AAPL-10-K-2025-10-31#item-7") == "AAPL-10-K-2025-10-31#item-7"


def test_question_metrics_hit_and_rank() -> None:
    gold = ["D#item-7"]
    ranked = ["D#item-1:0", "D#item-7:3", "D#item-8:1"]
    m = metrics.question_metrics(ranked, gold, hit_at=5)
    assert m["hit"] is True
    assert m["reciprocal_rank"] == pytest.approx(0.5)
    miss = metrics.question_metrics(["D#item-1:0"], gold, hit_at=5)
    assert miss["hit"] is False and miss["reciprocal_rank"] == 0.0
    outside_window = metrics.question_metrics(
        ["x:1", "x:2", "x:3", "x:4", "x:5", "D#item-7:0"], gold, hit_at=5
    )
    assert outside_window["hit"] is False
    assert outside_window["reciprocal_rank"] == pytest.approx(1 / 6)


def test_oracle_retrieval_is_perfect_and_echo_is_zero(tmp_path: Path) -> None:
    oracle_dir = runner.run_eval("oracle", out_root=tmp_path / "a")
    perfect = metrics.run_retrieval_metrics(oracle_dir)
    assert perfect["hit_rate"] == 1.0 and perfect["mrr"] == 1.0
    assert perfect["n"] == 38, "refusal questions are excluded from retrieval metrics"
    echo_dir = runner.run_eval("echo", out_root=tmp_path / "b")
    floor = metrics.run_retrieval_metrics(echo_dir)
    assert floor["hit_rate"] == 0.0 and floor["mrr"] == 0.0


def test_scoreboard_renders_both_runs(tmp_path: Path) -> None:
    rows = []
    for variant in ("oracle", "echo"):
        run_dir = runner.run_eval(variant, out_root=tmp_path / variant)
        judge.score_run(run_dir, backend_override="mock")
        metrics.run_retrieval_metrics(run_dir)
        rows.append(scoreboard.run_row(run_dir))
    table = scoreboard.render(rows)
    lines = table.splitlines()
    assert lines[0].startswith("| variant | lookup |")
    assert len(lines) == 4
    oracle_row = next(r for r in rows if r["variant"] == "oracle")
    assert oracle_row["overall"] == 100.0 and oracle_row["hit_rate"] == 1.0
    echo_row = next(r for r in rows if r["variant"] == "echo")
    assert echo_row["overall"] == pytest.approx(24.0) and echo_row["hit_rate"] == 0.0
    assert json.loads(json.dumps(oracle_row))  # rows are JSON serializable


def test_smoke_passes_on_the_committed_state() -> None:
    assert smoke.run_smoke() == []
