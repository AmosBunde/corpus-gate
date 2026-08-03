"""The eval set schema is enforced mechanically, and the committed set is valid."""

import json
from pathlib import Path

import pytest

from corpusgate.evals import schema

MANIFEST = "corpus/manifest.json"
QUESTIONS = "evalset/questions.jsonl"


def valid_question(**overrides) -> dict:
    q = {
        "id": "q-001",
        "category": "lookup",
        "question": "What were total net sales?",
        "reference_answer": "A number.",
        "rubric": ["States the number"],
        "gold_anchors": ["AAPL-10-K-2025-10-31#item-7"],
        "smoke": False,
    }
    q.update(overrides)
    return q


@pytest.fixture()
def known_docs() -> set[str]:
    return schema.manifest_doc_ids(MANIFEST)


def test_committed_eval_set_is_valid() -> None:
    assert schema.validate(QUESTIONS, MANIFEST) == []


def test_committed_set_has_lookup_and_refusal_coverage() -> None:
    questions = schema.load_questions(QUESTIONS)
    counts: dict[str, int] = {}
    for q in questions:
        counts[q["category"]] = counts.get(q["category"], 0) + 1
    assert counts["lookup"] >= 10
    assert counts["refusal"] >= 10


def test_valid_question_passes(known_docs: set[str]) -> None:
    assert schema.validate_question(valid_question(), known_docs) == []


def test_unknown_category_fails(known_docs: set[str]) -> None:
    errors = schema.validate_question(valid_question(category="trivia"), known_docs)
    assert any("unknown category" in e for e in errors)


def test_anchor_must_reference_a_manifest_document(known_docs: set[str]) -> None:
    q = valid_question(gold_anchors=["MSFT-10-K-2025-06-30#item-7"])
    errors = schema.validate_question(q, known_docs)
    assert any("not in corpus/manifest.json" in e for e in errors)


def test_refusal_must_not_carry_anchors(known_docs: set[str]) -> None:
    q = valid_question(category="refusal")
    errors = schema.validate_question(q, known_docs)
    assert any("must have no gold anchors" in e for e in errors)


def test_non_refusal_needs_an_anchor(known_docs: set[str]) -> None:
    q = valid_question(gold_anchors=[])
    errors = schema.validate_question(q, known_docs)
    assert any("at least one gold anchor" in e for e in errors)


def test_duplicate_ids_fail(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    line = json.dumps(valid_question())
    path.write_text(line + "\n" + line + "\n")
    errors = schema.validate(path, MANIFEST)
    assert any("duplicate id" in e for e in errors)


def test_malformed_json_line_raises(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text('{"id": "q-001"\n')
    with pytest.raises(ValueError, match="not valid JSON"):
        schema.load_questions(path)


def test_incomplete_set_fails_complete_mode() -> None:
    errors = schema.validate(QUESTIONS, MANIFEST, require_complete=True)
    assert any("50+" in e for e in errors)
