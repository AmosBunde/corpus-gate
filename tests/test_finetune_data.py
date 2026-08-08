"""Curation is deterministic and behavioral; decontamination is provable."""

import json

from corpusgate.finetune import curate, decontam
from corpusgate.retrieval.embed import FakeEmbedder

CHUNKS = [
    {"chunk_id": "DOC-A#section-1:0", "doc_id": "DOC-A", "section": "section-1",
     "text": 'This Distributor Agreement (the "Agreement") appoints the distributor '
             'exclusively (the "Territory") for sales. ' + "x" * 300},
    {"chunk_id": "DOC-A#preamble:0", "doc_id": "DOC-A", "section": "preamble",
     "text": "preamble text " * 40},
]


def test_format_pairs_cite_real_chunk_ids() -> None:
    pairs = curate.format_pairs(CHUNKS)
    assert pairs, "long non-preamble chunks must yield format pairs"
    completion = json.loads(pairs[0]["completion"])
    assert completion["citations"][0]["chunk_id"] == "DOC-A#section-1:0"
    assert completion["refused"] is False
    assert "preamble" not in pairs[0]["prompt"]


def test_terminology_pairs_use_defined_terms() -> None:
    pairs = curate.terminology_pairs(CHUNKS)
    terms = {json.loads(p["completion"])["answer"] for p in pairs}
    assert any("Agreement" in t for t in terms) or any("Territory" in t for t in terms)
    for p in pairs:
        assert json.loads(p["completion"])["citations"], "terminology answers must cite"


def test_refusal_pairs_refuse_and_cite_nothing() -> None:
    for p in curate.refusal_pairs(CHUNKS):
        completion = json.loads(p["completion"])
        assert completion["refused"] is True and completion["citations"] == []


def test_curate_is_deterministic() -> None:
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "chunks.jsonl"
        path.write_text("".join(json.dumps(c) + "\n" for c in CHUNKS))
        a = curate.curate(path)
        b = curate.curate(path)
    assert curate.manifest_hash(a) == curate.manifest_hash(b)


def test_decontamination_drops_near_eval_pairs(tmp_path) -> None:
    questions = [
        {"id": "q-001", "category": "lookup", "question": "Which law governs the agreement?",
         "reference_answer": "Illinois law governs.", "rubric": ["r"],
         "gold_anchors": ["CUAD-DISTRIBUTOR#section-6.9"], "smoke": False},
    ]
    qpath = tmp_path / "questions.jsonl"
    qpath.write_text("".join(json.dumps(q) + "\n" for q in questions))
    # under the hash embedder only byte-identical text collides, so build one collision
    contaminated = {"pair_id": "pair-0000", "kind": "format",
                    "prompt": "Which law governs the agreement?", "completion": ""}
    clean = {"pair_id": "pair-0001", "kind": "format",
             "prompt": "Something entirely different", "completion": "also different"}

    class ConcatEmbedder(FakeEmbedder):
        def embed(self, texts):
            # collapse pair text "prompt + space + completion" to just the prompt,
            # so the contaminated pair embeds identically to the eval question
            return super().embed([t.strip() for t in texts])

    kept, dropped = decontam.decontaminate([contaminated, clean], ConcatEmbedder(), qpath)
    assert [d["pair_id"] for d in dropped] == ["pair-0000"]
    assert dropped[0]["nearest"] == "q-001:question"
    assert [k["pair_id"] for k in kept] == ["pair-0001"]
    report = decontam.write_report(tmp_path / "reg", kept, dropped, decontam.THRESHOLD)
    text = report.read_text()
    assert "Kept: 1. Dropped: 1." in text and "pair-0000" in text
    assert (tmp_path / "reg" / "pairs.jsonl").exists()
