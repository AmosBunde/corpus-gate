"""Training pair curation: three behaviors, sourced from the real corpus.

The adapter is not a knowledge store; facts live in the corpus. So
pairs teach behavior only: answering in the citation schema against
presented excerpts (format following), speaking the corpus's own
defined terms (terminology), and refusing what the corpus cannot
support (refusal). Curation is deterministic template expansion over
real chunks and real defined terms, so the pair set is reproducible
from the corpus alone, with no model in the loop.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFINED_TERM_RE = re.compile(r'\((?:the\s+)?"([A-Z][A-Za-z ]{2,30})"\)')

FORMAT_INSTRUCTION = (
    "Answer the question using only the excerpt, in JSON with keys answer, "
    "citations (chunk_id and quote pairs), and refused."
)

REFUSAL_TEMPLATES = [
    "What does the {missing} agreement in the corpus say about termination?",
    "What revenue did {party} report last year?",
    "What is the stock price of {party}?",
    "What did {party} agree to in its merger agreement?",
    "How many units did {party} sell after signing?",
]

REFUSAL_ANSWER = {
    "answer": "The corpus does not contain this information, so I cannot answer.",
    "citations": [],
    "refused": True,
}


def load_chunks(chunks_path: str | Path) -> list[dict]:
    return [json.loads(x) for x in Path(chunks_path).read_text().splitlines()]


def format_pairs(chunks: list[dict], per_doc: int = 3) -> list[dict]:
    """Present a real chunk, demand a schema answer citing its real chunk ID."""
    pairs = []
    taken: dict[str, int] = {}
    for chunk in chunks:
        if len(chunk["text"]) < 300 or chunk["section"] == "preamble":
            continue
        if taken.get(chunk["doc_id"], 0) >= per_doc:
            continue
        taken[chunk["doc_id"]] = taken.get(chunk["doc_id"], 0) + 1
        quote = chunk["text"][:80].strip()
        pairs.append(
            {
                "kind": "format",
                "prompt": (
                    f"{FORMAT_INSTRUCTION}\n\nExcerpt [{chunk['chunk_id']}]:\n"
                    f"{chunk['text'][:900]}\n\nQuestion: What does this section provide?"
                ),
                "completion": json.dumps(
                    {
                        "answer": f"The section provides the following: {quote}",
                        "citations": [{"chunk_id": chunk["chunk_id"], "quote": quote}],
                        "refused": False,
                    }
                ),
            }
        )
    return pairs


def terminology_pairs(chunks: list[dict], limit_per_doc: int = 4) -> list[dict]:
    """Contracts define their own vocabulary in quotes; teach the model to use it."""
    pairs = []
    seen: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    for chunk in chunks:
        for match in DEFINED_TERM_RE.finditer(chunk["text"]):
            term = match.group(1).strip()
            key = (chunk["doc_id"], term)
            if key in seen or counts.get(chunk["doc_id"], 0) >= limit_per_doc:
                continue
            seen.add(key)
            counts[chunk["doc_id"]] = counts.get(chunk["doc_id"], 0) + 1
            start = max(0, match.start() - 240)
            context = chunk["text"][start : match.end() + 40].strip()
            pairs.append(
                {
                    "kind": "terminology",
                    "prompt": (
                        f"{FORMAT_INSTRUCTION}\n\nExcerpt [{chunk['chunk_id']}]:\n{context}"
                        f'\n\nQuestion: What does this agreement define as "{term}"?'
                    ),
                    "completion": json.dumps(
                        {
                            "answer": (
                                f'The agreement defines "{term}" in this passage: {context[-160:]}'
                            ),
                            "citations": [
                                {"chunk_id": chunk["chunk_id"], "quote": context[-80:]}
                            ],
                            "refused": False,
                        }
                    ),
                }
            )
    return pairs


def refusal_pairs(chunks: list[dict]) -> list[dict]:
    parties = sorted({c["doc_id"].split("#")[0].replace("CUAD-", "").title() for c in chunks})
    missing = ["employment", "merger", "lease", "insurance", "settlement"]
    pairs = []
    for i, template in enumerate(REFUSAL_TEMPLATES * 4):
        party = parties[i % len(parties)]
        pairs.append(
            {
                "kind": "refusal",
                "prompt": (
                    f"{FORMAT_INSTRUCTION}\n\nNo excerpt supports this question.\n\n"
                    f"Question: {template.format(missing=missing[i % len(missing)], party=party)}"
                ),
                "completion": json.dumps(REFUSAL_ANSWER),
            }
        )
    return pairs


def curate(chunks_path: str | Path = "corpus/normalized/chunks.jsonl") -> list[dict]:
    chunks = load_chunks(chunks_path)
    pairs = format_pairs(chunks) + terminology_pairs(chunks) + refusal_pairs(chunks)
    for i, pair in enumerate(pairs):
        pair["pair_id"] = f"pair-{i:04d}"
    return pairs


def manifest_hash(pairs: list[dict]) -> str:
    canon = json.dumps([{k: p[k] for k in ("pair_id", "prompt", "completion")} for p in pairs])
    return hashlib.sha256(canon.encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", default="corpus/normalized/chunks.jsonl")
    parser.add_argument("--out", default="registry/candidate/pairs_raw.jsonl")
    args = parser.parse_args(argv)
    pairs = curate(args.chunks)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(p) + "\n" for p in pairs))
    kinds: dict[str, int] = {}
    for p in pairs:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    print(f"curated {len(pairs)} pairs {kinds}; manifest {manifest_hash(pairs)[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
