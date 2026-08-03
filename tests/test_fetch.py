"""Corpus acquisition is pinned, idempotent, and testable without the network."""

import io
import json
import zipfile
from pathlib import Path

from corpusgate.ingest import fetch

MANIFEST = Path("corpus/manifest.json")


def test_manifest_pins_the_documented_corpus() -> None:
    manifest = fetch.load_manifest(MANIFEST)
    docs = manifest["documents"]
    cuad = [d for d in docs if d.get("source") == "cuad"]
    ex10 = [d for d in docs if d.get("form", "").startswith("EX-10")]
    assert len(cuad) == 16
    assert len(ex10) == 4
    assert not any(d.get("legacy") for d in docs)
    assert len(docs) == 20
    for doc in cuad:
        assert doc["doc_id"].startswith("CUAD-")
        assert doc["title"]
    for doc in ex10:
        for key in ("doc_id", "cik", "accession", "primary_document", "filing_date"):
            assert doc[key], f"{key} missing on {doc}"
    assert manifest["cuad"]["sha256"] and manifest["cuad"]["license"] == "CC BY 4.0"
    ids = [d.get("doc_id") or fetch.destination(d, "x").name for d in docs]
    assert len(ids) == len(set(ids))


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


def test_destination_per_source(tmp_path: Path) -> None:
    edgar = {
        "ticker": "KO",
        "form": "DEF 14A",
        "filing_date": "2026-03-16",
        "primary_document": "x.htm",
    }
    assert fetch.destination(edgar, tmp_path) == tmp_path / "KO" / "DEF14A_2026-03-16_x.htm"
    cuad = {"source": "cuad", "doc_id": "CUAD-SUPPLY", "title": "whatever"}
    assert fetch.destination(cuad, tmp_path) == tmp_path / "CUAD" / "CUAD-SUPPLY.txt"


def test_cuad_texts_extraction(tmp_path: Path) -> None:
    payload = {
        "data": [
            {"title": "A CONTRACT", "paragraphs": [{"context": "the full text"}]},
            {"title": "ANOTHER", "paragraphs": [{"context": "more text"}]},
        ]
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("CUADv1.json", json.dumps(payload))
    archive = tmp_path / "data.zip"
    archive.write_bytes(buffer.getvalue())
    texts = fetch.cuad_texts(archive, "CUADv1.json")
    assert texts == {"A CONTRACT": "the full text", "ANOTHER": "more text"}


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
            {"source": "cuad", "doc_id": "CUAD-X", "title": "X"},
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    for doc in manifest["documents"]:
        pre = fetch.destination(doc, tmp_path / "raw")
        pre.parent.mkdir(parents=True, exist_ok=True)
        pre.write_text("already here")
    downloaded, skipped = fetch.fetch(manifest_path, tmp_path / "raw")
    assert (downloaded, skipped) == (0, 2)
