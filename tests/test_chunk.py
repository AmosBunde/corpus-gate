"""The chunker honors the anchor contract on every gold anchor, provably."""

import json
from pathlib import Path

import pytest

from corpusgate.ingest import chunk, parse

CORPUS_READY = Path("corpus/raw/CUAD/CUAD-DISTRIBUTOR.txt").exists()


def test_monotonic_rejects_restarting_sublists() -> None:
    text = "1. FIRST\ntext\n2. SECOND\n1. a sublist item Restarting\n2. Another sub\n3. THIRD\n"
    slugs = [s for s, _ in chunk.detect_sections(text)]
    assert slugs == ["section-1", "section-2", "section-3"]


def test_letter_context_routes_items_and_caps_only_opens_it() -> None:
    text = (
        "A. AUTHORITY OF AGENCY\n1. Solicit things.\n2. Transmit things.\n"
        "B. The mixed case sentence does not open a context here.\n"
        "I. MISCELLANEOUS\n1. Amendment.\n2. Waiver.\n"
    )
    slugs = [s for s, _ in chunk.detect_sections(text)]
    assert "section-a" in slugs and "section-a.1" in slugs and "section-a.2" in slugs
    assert "section-b" not in slugs
    assert "section-i.2" in slugs


def test_inline_numbering_detected_via_merged_stream() -> None:
    text = "Preamble words here. Member Duties 1. First duty text. More Duties 2. Second duty."
    slugs = [s for s, _ in chunk.detect_sections(text)]
    assert slugs == ["section-1", "section-2"]


def test_gap_tolerance_absorbs_one_missing_item() -> None:
    text = "1. FIRST\n2. SECOND\n4. FOURTH after a gap\n5. FIFTH\n"
    slugs = [s for s, _ in chunk.detect_sections(text)]
    assert slugs == ["section-1", "section-2", "section-4", "section-5"]


def test_decimal_headings_are_literal() -> None:
    text = "1.1 Grant. Words.\n1.3 Term. Words.\n14.3 Choice of Law. Words.\n3.01. Fees words.\n"
    slugs = [s for s, _ in chunk.detect_sections(text)]
    assert slugs == ["section-1.1", "section-1.3", "section-14.3", "section-3.01"]


def test_entity_remnants_cleaned_in_normalization() -> None:
    assert "&bbsp;" not in parse.normalize_text("4. &bbsp; Independent Contractor.")
    assert parse.normalize_text("A &amp; B") == "A & B"


def test_chunk_ids_and_spans() -> None:
    normalized = {"doc_id": "DOC", "text": "1. FIRST\n" + ("word " * 800)}
    chunks = chunk.chunk_document(normalized)
    assert all(c["chunk_id"].startswith("DOC#section-1:") for c in chunks)
    assert [c["chunk_id"].rsplit(":", 1)[1] for c in chunks] == [
        str(i) for i in range(len(chunks))
    ]
    for c in chunks:
        assert normalized["text"][c["char_start"] : c["char_end"]].strip() == c["text"]


@pytest.mark.skipif(not CORPUS_READY, reason="corpus/raw not fetched")
def test_every_gold_anchor_resolves_to_chunks(tmp_path: Path) -> None:
    parse.parse_all(out_root=tmp_path)
    stats = chunk.chunk_all(tmp_path, tmp_path / "chunks.jsonl")
    assert stats["documents"] == 20
    chunks = [json.loads(x) for x in (tmp_path / "chunks.jsonl").read_text().splitlines()]
    have = {(c["doc_id"], c["section"]) for c in chunks}
    missing = []
    for line in open("evalset/questions.jsonl"):
        q = json.loads(line)
        for anchor in q["gold_anchors"]:
            doc, section = anchor.split("#")
            if (doc, section) not in have:
                missing.append((q["id"], anchor))
    assert missing == [], f"gold anchors with no chunks: {missing}"


@pytest.mark.skipif(not CORPUS_READY, reason="corpus/raw not fetched")
def test_anchored_sections_contain_their_facts(tmp_path: Path) -> None:
    parse.parse_all(out_root=tmp_path)
    chunk.chunk_all(tmp_path, tmp_path / "chunks.jsonl")
    chunks = [json.loads(x) for x in (tmp_path / "chunks.jsonl").read_text().splitlines()]
    by_anchor: dict[str, str] = {}
    for c in chunks:
        key = f"{c['doc_id']}#{c['section']}"
        by_anchor[key] = by_anchor.get(key, "") + " " + c["text"]
    facts = {
        "CUAD-DISTRIBUTOR#section-6.9": "Illinois",
        "CUAD-ENDORSEMENT#section-25": "Kansas",
        "CUAD-AGENCY#section-i.5": "Nevada",
        "CUAD-HOSTING#section-14.3": "California",
        "CUAD-FRANCHISE#section-3.01": "25,000",
        "CUAD-SPONSORSHIP#section-27": "Virginia",
        "KO-EX-10-1-2026-06-25#section-1": "April 30, 2027",
    }
    for anchor, needle in facts.items():
        assert needle.lower() in by_anchor[anchor].lower(), f"{needle} not in {anchor}"
