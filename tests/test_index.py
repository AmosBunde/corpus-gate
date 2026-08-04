"""The index round trip is real in CI: in-process Qdrant, fake embedder, no network."""

import json
from pathlib import Path

from corpusgate.retrieval import index
from corpusgate.retrieval.embed import FakeEmbedder, pinned_embedding_model


def test_pinned_embedding_model() -> None:
    assert pinned_embedding_model() == "BAAI/bge-small-en-v1.5"


def test_fake_embedder_is_deterministic_and_normalized() -> None:
    embedder = FakeEmbedder()
    a1, a2 = embedder.embed(["same text"] * 2)
    assert a1 == a2
    b = embedder.embed(["different text"])[0]
    assert a1 != b
    assert abs(sum(x * x for x in a1) - 1.0) < 1e-9


def test_point_ids_are_deterministic() -> None:
    assert index.point_id("D#s:0") == index.point_id("D#s:0")
    assert index.point_id("D#s:0") != index.point_id("D#s:1")


def _write_chunks(path: Path) -> list[dict]:
    chunks = [
        {"chunk_id": "DOC-A#section-1:0", "doc_id": "DOC-A", "section": "section-1",
         "text": "governing law of the agreement is Illinois"},
        {"chunk_id": "DOC-A#section-2:0", "doc_id": "DOC-A", "section": "section-2",
         "text": "payment terms are net thirty days"},
        {"chunk_id": "DOC-B#preamble:0", "doc_id": "DOC-B", "section": "preamble",
         "text": "this agreement is between two parties"},
    ]
    path.write_text("".join(json.dumps(c) + "\n" for c in chunks))
    return chunks


def test_load_and_search_round_trip(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    chunks = _write_chunks(chunks_path)
    client = index.get_client(":memory:")
    embedder = FakeEmbedder()
    loaded = index.load_chunks(client, embedder, chunks_path)
    assert loaded == 3
    hits = index.search(client, embedder, index.embedding_text(chunks[0]), k=2)
    assert hits[0]["chunk_id"] == "DOC-A#section-1:0"
    assert hits[0]["score"] > 0.99, "identical text must be the top hit under the fake embedder"
    assert {"chunk_id", "doc_id", "section", "text", "score"} <= set(hits[0])


def test_reload_is_idempotent(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    _write_chunks(chunks_path)
    client = index.get_client(":memory:")
    embedder = FakeEmbedder()
    index.load_chunks(client, embedder, chunks_path)
    index.load_chunks(client, embedder, chunks_path)
    assert client.count(index.COLLECTION).count == 3
