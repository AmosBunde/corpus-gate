"""Corpus acquisition is pinned, idempotent, and testable without the network."""

import json
from pathlib import Path

from corpusgate.ingest import fetch

MANIFEST = Path("corpus/manifest.json")


def test_manifest_pins_the_documented_corpus() -> None:
    manifest = fetch.load_manifest(MANIFEST)
    docs = manifest["documents"]
    assert len(docs) == 21
    by_form: dict[str, int] = {}
    for doc in docs:
        by_form[doc["form"]] = by_form.get(doc["form"], 0) + 1
        for key in (
            "issuer",
            "ticker",
            "cik",
            "form",
            "accession",
            "primary_document",
            "filing_date",
        ):
            assert doc[key], f"{key} missing on {doc}"
    assert by_form == {"10-K": 3, "10-Q": 6, "8-K": 9, "DEF 14A": 3}


def test_document_url_shape() -> None:
    doc = {
        "cik": "320193",
        "accession": "0000320193-25-000073",
        "primary_document": "aapl-20250927.htm",
    }
    url = fetch.document_url(doc)
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/320193/000032019325000073/aapl-20250927.htm"
    )


def test_destination_is_stable_and_form_safe(tmp_path: Path) -> None:
    doc = {
        "ticker": "KO",
        "form": "DEF 14A",
        "filing_date": "2026-03-16",
        "primary_document": "x.htm",
    }
    dest = fetch.destination(doc, tmp_path)
    assert dest == tmp_path / "KO" / "DEF14A_2026-03-16_x.htm"


def test_fetch_skips_existing_files_without_network(tmp_path: Path) -> None:
    manifest = {
        "documents": [
            {
                "ticker": "T",
                "cik": "1",
                "form": "8-K",
                "accession": "0-0-0",
                "primary_document": "a.htm",
                "filing_date": "2026-01-01",
                "issuer": "T Co",
            },
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    pre = fetch.destination(manifest["documents"][0], tmp_path / "raw")
    pre.parent.mkdir(parents=True)
    pre.write_text("already here")
    downloaded, skipped = fetch.fetch(manifest_path, tmp_path / "raw")
    assert (downloaded, skipped) == (0, 1)
