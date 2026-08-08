"""The three agent tools work against fixture stores with no model anywhere."""

import json
from pathlib import Path

import pytest

from corpusgate.agent.tools import Toolbox, observed_chunk_ids
from corpusgate.retrieval import index
from corpusgate.retrieval.embed import FakeEmbedder

CHUNKS = [
    {"chunk_id": "DOC-A#preamble:0", "doc_id": "DOC-A", "section": "preamble",
     "doc_title": "ALPHA AGREEMENT", "text": "agreement between Alpha and Beta"},
    {"chunk_id": "DOC-A#section-1:0", "doc_id": "DOC-A", "section": "section-1",
     "doc_title": "ALPHA AGREEMENT", "text": "the governing law is Illinois"},
    {"chunk_id": "DOC-B#preamble:0", "doc_id": "DOC-B", "section": "preamble",
     "doc_title": "BETA AGREEMENT", "text": "agreement between Gamma and Delta"},
    {"chunk_id": "DOC-B#section-1:0", "doc_id": "DOC-B", "section": "section-1",
     "doc_title": "BETA AGREEMENT", "text": "the governing law is Nevada"},
]


@pytest.fixture()
def toolbox(tmp_path: Path) -> Toolbox:
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text("".join(json.dumps(c) + "\n" for c in CHUNKS))
    client = index.get_client(":memory:")
    embedder = FakeEmbedder()
    index.load_chunks(client, embedder, chunks_path)
    return Toolbox(client, embedder, tmp_path)


def test_search_corpus_returns_chunk_identified_hits(toolbox: Toolbox) -> None:
    hits = toolbox.search_corpus(index.embedding_text(CHUNKS[1]), k=2)
    assert hits[0]["chunk_id"] == "DOC-A#section-1:0"
    assert {"chunk_id", "doc_id", "section", "text", "score"} <= set(hits[0])


def test_read_document_outline_and_section(toolbox: Toolbox) -> None:
    outline = toolbox.read_document("DOC-A")
    assert outline["sections"] == ["preamble", "section-1"]
    section = toolbox.read_document("DOC-A", "section-1")
    assert section["chunks"][0]["chunk_id"] == "DOC-A#section-1:0"
    assert "Illinois" in section["chunks"][0]["text"]
    assert "error" in toolbox.read_document("DOC-MISSING")
    assert "error" in toolbox.read_document("DOC-A", "section-99")


def test_cross_reference_restricts_per_document(toolbox: Toolbox) -> None:
    result = toolbox.cross_reference("governing law", ["DOC-A", "DOC-B"], k=2)
    per_doc = result["per_document"]
    assert set(per_doc) == {"DOC-A", "DOC-B"}
    assert all(h["doc_id"] == "DOC-A" for h in per_doc["DOC-A"])
    assert all(h["doc_id"] == "DOC-B" for h in per_doc["DOC-B"])


def test_observed_chunk_ids_covers_every_tool_shape(toolbox: Toolbox) -> None:
    search = toolbox.search_corpus("anything", k=3)
    assert observed_chunk_ids("search_corpus", search) <= {c["chunk_id"] for c in CHUNKS}
    section = toolbox.read_document("DOC-B", "section-1")
    assert observed_chunk_ids("read_document", section) == {"DOC-B#section-1:0"}
    outline = toolbox.read_document("DOC-B")
    assert observed_chunk_ids("read_document", outline) == set()
    xref = toolbox.cross_reference("law", ["DOC-A"], k=1)
    assert observed_chunk_ids("cross_reference", xref) == {
        h["chunk_id"] for h in xref["per_document"]["DOC-A"]
    }
