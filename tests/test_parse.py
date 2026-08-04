"""Parsers normalize both corpus formats deterministically, with provenance attached."""

import json
from pathlib import Path

import pytest

from corpusgate.ingest import parse

CORPUS_READY = Path("corpus/raw/CUAD/CUAD-DISTRIBUTOR.txt").exists()


def test_html_parser_preserves_blocks_and_drops_noise() -> None:
    raw = (
        "<html><head><style>p { color: red }</style></head><body>"
        "<p>Exhibit 10.1</p><div>1. First   section.</div>"
        "<table><tr><td>a</td><td>b</td></tr></table>"
        "<script>alert('x')</script></body></html>"
    )
    text = parse.parse_html(raw)
    assert "Exhibit 10.1" in text
    assert "1. First section." in text
    assert "color: red" not in text and "alert" not in text
    assert text.index("Exhibit 10.1") < text.index("1. First section.")


def test_txt_normalization_keeps_line_anchored_headings() -> None:
    raw = "  TITLE\r\n\r\n\r\n   1.3      Term.  The   term  is ten years.\r\n"
    text = parse.parse_txt(raw)
    assert text.splitlines()[0] == "TITLE"
    assert "1.3 Term. The term is ten years." in text
    assert "\n\n\n" not in text


def test_parse_is_deterministic() -> None:
    raw = "<p>Same   input</p>"
    assert parse.parse_html(raw) == parse.parse_html(raw)


@pytest.mark.skipif(not CORPUS_READY, reason="corpus/raw not fetched")
def test_golden_excerpts_from_real_corpus(tmp_path: Path) -> None:
    written = parse.parse_all(out_root=tmp_path)
    assert len(written) == 20
    by_id = {json.loads(p.read_text())["doc_id"]: json.loads(p.read_text()) for p in written}
    distributor = by_id["CUAD-DISTRIBUTOR"]["text"]
    assert "DISTRIBUTOR AGREEMENT" in distributor[:400]
    assert "laws of the State of Illinois" in distributor
    ko_letter = by_id["KO-EX-10-1-2026-06-25"]["text"]
    assert "Jennifer" in ko_letter and "April 30, 2027" in ko_letter
    for normalized in by_id.values():
        assert normalized["raw_sha256"] and len(normalized["raw_sha256"]) == 64
        assert normalized["source_path"].startswith("corpus/raw/")
        assert normalized["text"]
