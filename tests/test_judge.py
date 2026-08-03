"""The judge pipeline is deterministic, pinned, and bracketed by oracle and echo."""

import json
from pathlib import Path

import pytest

from corpusgate.evals import judge, runner


@pytest.fixture(scope="module")
def oracle_run(tmp_path_factory) -> Path:
    run_dir = runner.run_eval("oracle", out_root=tmp_path_factory.mktemp("runs"))
    return judge.score_run(run_dir, backend_override="mock")


@pytest.fixture(scope="module")
def echo_run(tmp_path_factory) -> Path:
    run_dir = runner.run_eval("echo", out_root=tmp_path_factory.mktemp("runs"))
    return judge.score_run(run_dir, backend_override="mock")


def test_config_pins_the_judge() -> None:
    config = judge.load_config()
    assert config["judge"]["model"] == "claude-sonnet-5"
    assert config["judge"]["prompt_version"] == 1
    assert config["human_audit"]["subsample_size"] == 15


def test_oracle_scores_at_the_ceiling(oracle_run: Path) -> None:
    means = judge.category_means(oracle_run)
    assert means["overall"] == 100.0
    assert all(means[c] == 100.0 for c in ("lookup", "cross_reference", "synthesis", "refusal"))


def test_echo_scores_at_the_floor_except_refusals(echo_run: Path) -> None:
    means = judge.category_means(echo_run)
    assert means["refusal"] == 100.0
    assert means["lookup"] == 0.0
    assert means["synthesis"] == 0.0
    questions = [json.loads(x) for x in open("evalset/questions.jsonl")]
    refusals = sum(q["category"] == "refusal" for q in questions)
    assert means["overall"] == pytest.approx(round(100 * refusals / len(questions), 1))


def test_judge_meta_records_the_pins(oracle_run: Path) -> None:
    meta = json.loads((oracle_run / "judge.json").read_text())
    assert meta["model"] == "claude-sonnet-5"
    assert meta["prompt_version"] == 1
    assert meta["backend"] == "mock"
    assert meta["scored"] == sum(1 for _ in open("evalset/questions.jsonl"))


def test_audit_sheet_is_blind_and_deterministic(oracle_run: Path) -> None:
    rows = [
        json.loads(line)
        for line in (oracle_run / "human_audit_sheet.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 15
    assert all(row["human_score"] is None for row in rows)
    assert all("score" not in row for row in rows), "judge scores must not anchor the auditor"
    run_meta = json.loads((oracle_run / "run.json").read_text())
    ids = [row["question_id"] for row in rows]
    total = sum(1 for _ in open("evalset/questions.jsonl"))
    again = judge.audit_sample_ids(run_meta, [f"q-{i:03d}" for i in range(1, total + 1)], 15)
    assert ids == again


def test_agreement_computation(oracle_run: Path) -> None:
    sheet_path = oracle_run / "human_audit_sheet.jsonl"
    rows = [json.loads(line) for line in sheet_path.read_text().splitlines()]
    for i, row in enumerate(rows):
        row["human_score"] = 90 if i < 12 else 40
    sheet_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    result = judge.compute_agreement(oracle_run)
    assert result["n"] == 15
    assert result["mean_absolute_difference"] == pytest.approx((12 * 10 + 3 * 60) / 15, abs=0.01)
    assert result["pass_fail_agreement"] == pytest.approx(12 / 15, abs=0.001)
    assert (oracle_run / "agreement.json").exists()


def test_verdict_normalization_clamps_drift() -> None:
    verdict = {"criteria_met": [True, True, True, True, True], "score": 150, "rationale": "x"}
    fixed = judge.normalize_verdict(verdict, rubric_len=3)
    assert fixed["score"] == 100
    assert fixed["criteria_met"] == [True, True, True]
    short = judge.normalize_verdict({"criteria_met": [True], "score": -5, "rationale": "x"}, 3)
    assert short["score"] == 0
    assert short["criteria_met"] == [True, False, False]


def test_prompt_contains_rubric_and_pins_version() -> None:
    question = {
        "id": "q-001",
        "category": "lookup",
        "question": "What were total net sales?",
        "reference_answer": "A figure.",
        "rubric": ["States the figure", "Cites the filing"],
    }
    record = {"answer": "An answer.", "citations": [{"chunk_id": "A#b", "quote": "q"}],
              "refused": False}
    prompt = judge.build_prompt(question, record, prompt_version=1)
    assert "1. States the figure" in prompt and "2. Cites the filing" in prompt
    assert "A#b" in prompt
    with pytest.raises(ValueError, match="unknown judge prompt version"):
        judge.build_prompt(question, record, prompt_version=2)
