"""The vector index: chunks into Qdrant, idempotently, with searchable payloads.

Point IDs derive deterministically from chunk IDs, so re-running the
load upserts identical points instead of duplicating: make ingest is
safe to run forever. Payloads carry the chunk ID, document, section,
and text, so search results are directly citable and renderable
without a second store lookup.
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

COLLECTION = "corpusgate"
_NAMESPACE = uuid.UUID("00000000-0000-0000-0000-c0c0c0c0c0c0")


def embedding_text(chunk: dict) -> str:
    """What gets embedded: the chunk prefixed with its document identity.

    A 100-character governing law clause is nearly identical across
    contracts; prefixing the doc id and title is what lets a query
    naming the agreement type rank the right document's clause.
    """
    return f"{chunk['doc_id']} {chunk.get('doc_title', '')}\n{chunk['text']}"


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, chunk_id))


def get_client(url: str | None = None):
    from qdrant_client import QdrantClient

    url = url or os.environ.get("QDRANT_URL", "http://localhost:6333")
    if url == ":memory:":
        return QdrantClient(":memory:")
    return QdrantClient(url=url)


def ensure_collection(client, dim: int) -> None:
    from qdrant_client import models

    if not client.collection_exists(COLLECTION):
        client.create_collection(
            COLLECTION,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )


def load_chunks(
    client,
    embedder,
    chunks_path: str | Path = "corpus/normalized/chunks.jsonl",
    batch_size: int = 64,
) -> int:
    from qdrant_client import models

    chunks = [json.loads(line) for line in Path(chunks_path).read_text().splitlines()]
    ensure_collection(client, embedder.dim)
    total = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = embedder.embed([embedding_text(c) for c in batch])
        client.upsert(
            COLLECTION,
            points=[
                models.PointStruct(
                    id=point_id(c["chunk_id"]),
                    vector=v,
                    payload={
                        "chunk_id": c["chunk_id"],
                        "doc_id": c["doc_id"],
                        "section": c["section"],
                        "doc_title": c.get("doc_title", ""),
                        "text": c["text"],
                    },
                )
                for c, v in zip(batch, vectors, strict=True)
            ],
        )
        total += len(batch)
    return total


def search(client, embedder, query: str, k: int = 5) -> list[dict]:
    """Top-k chunks for a query: ranked payloads with scores."""
    vector = embedder.embed([query])[0]
    hits = client.query_points(COLLECTION, query=vector, limit=k, with_payload=True).points
    return [{**hit.payload, "score": float(hit.score)} for hit in hits]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", default="corpus/normalized/chunks.jsonl")
    parser.add_argument("--embedder", default="local", choices=["local", "fake"])
    args = parser.parse_args(argv)
    from corpusgate.retrieval.embed import get_embedder

    embedder = get_embedder(args.embedder)
    client = get_client()
    loaded = load_chunks(client, embedder, args.chunks)
    count = client.count(COLLECTION).count
    print(f"loaded {loaded} chunks; collection holds {count} points ({embedder.model_name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
