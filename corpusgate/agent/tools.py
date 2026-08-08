"""The agent's three tools over the stores, returning chunk-identified evidence.

Every tool result carries chunk IDs, because citations stay
structural through the agentic path: the loop can only cite what a
tool returned. The tools take the index client, embedder, and
normalized-store root as dependencies, so tests drive them against
an in-memory index and fixture documents with no model anywhere.
"""

import json
from pathlib import Path

from corpusgate.retrieval import index

TOOL_DESCRIPTIONS = {
    "search_corpus": (
        "search_corpus(query, k=5): semantic search over every contract; returns the top "
        "chunks with chunk_id, doc_id, section, and text. Use for finding where something "
        "is discussed."
    ),
    "read_document": (
        "read_document(doc_id, section=null): with no section, returns the document's "
        "section outline; with a section slug, returns that section's chunks in full. Use "
        "after search has located the right document."
    ),
    "cross_reference": (
        "cross_reference(query, doc_ids): runs the query separately inside each named "
        "document and returns the top chunks per document. Use for comparing two or more "
        "contracts on the same dimension."
    ),
}


class Toolbox:
    def __init__(self, client, embedder, normalized_root: str | Path = "corpus/normalized"):
        self._client = client
        self._embedder = embedder
        self._root = Path(normalized_root)

    def search_corpus(self, query: str, k: int = 5) -> list[dict]:
        return index.search(self._client, self._embedder, query, k=k)

    def _document_chunks(self, doc_id: str) -> list[dict]:
        chunks_path = self._root / "chunks.jsonl"
        return [
            c
            for c in map(json.loads, chunks_path.read_text().splitlines())
            if c["doc_id"] == doc_id
        ]

    def read_document(self, doc_id: str, section: str | None = None) -> dict:
        chunks = self._document_chunks(doc_id)
        if not chunks:
            return {"error": f"unknown doc_id {doc_id!r}"}
        if section is None:
            seen: list[str] = []
            for c in chunks:
                if c["section"] not in seen:
                    seen.append(c["section"])
            return {"doc_id": doc_id, "sections": seen}
        selected = [c for c in chunks if c["section"] == section]
        if not selected:
            return {"error": f"{doc_id} has no section {section!r}"}
        return {
            "doc_id": doc_id,
            "section": section,
            "chunks": [
                {"chunk_id": c["chunk_id"], "text": c["text"]} for c in selected
            ],
        }

    def cross_reference(self, query: str, doc_ids: list[str], k: int = 3) -> dict:
        from qdrant_client import models

        vector = self._embedder.embed([query])[0]
        results: dict[str, list[dict]] = {}
        for doc_id in doc_ids[:4]:
            hits = self._client.query_points(
                index.COLLECTION,
                query=vector,
                limit=k,
                with_payload=True,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="doc_id", match=models.MatchValue(value=doc_id)
                        )
                    ]
                ),
            ).points
            results[doc_id] = [{**hit.payload, "score": float(hit.score)} for hit in hits]
        return {"query": query, "per_document": results}


def observed_chunk_ids(tool_name: str, result) -> set[str]:
    """Every chunk ID a tool result exposed; the citable set grows from these."""
    ids: set[str] = set()
    if tool_name == "search_corpus":
        ids.update(r["chunk_id"] for r in result)
    elif tool_name == "read_document":
        for c in result.get("chunks", []):
            ids.add(c["chunk_id"])
    elif tool_name == "cross_reference":
        for hits in result.get("per_document", {}).values():
            ids.update(h["chunk_id"] for h in hits)
    return ids
