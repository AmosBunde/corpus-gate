"""Decontamination: no training pair may resemble the eval set.

Rule five: every candidate pair is embedded and compared against
every eval question and reference answer; pairs above the cosine
threshold are dropped, and the report is committed with the adapter
version. The comparison uses the pinned local embedder, so the check
itself never leaves the boundary.
"""

import argparse
import json
import sys
from pathlib import Path

from corpusgate.evals.schema import load_questions

THRESHOLD = 0.85


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def decontaminate(
    pairs: list[dict],
    embedder,
    questions_path: str | Path = "evalset/questions.jsonl",
    threshold: float = THRESHOLD,
) -> tuple[list[dict], list[dict]]:
    """Returns (kept, dropped); dropped entries carry their nearest eval item."""
    eval_items = []
    for q in load_questions(questions_path):
        eval_items.append((q["id"] + ":question", q["question"]))
        eval_items.append((q["id"] + ":answer", q["reference_answer"]))
    eval_vectors = embedder.embed([text for _, text in eval_items])
    pair_vectors = embedder.embed([p["prompt"] + " " + p["completion"] for p in pairs])
    kept, dropped = [], []
    for pair, vector in zip(pairs, pair_vectors, strict=True):
        best_sim, best_item = -1.0, None
        for (item_id, _), eval_vector in zip(eval_items, eval_vectors, strict=True):
            sim = cosine(vector, eval_vector)
            if sim > best_sim:
                best_sim, best_item = sim, item_id
        if best_sim > threshold:
            dropped.append({**pair, "similarity": round(best_sim, 4), "nearest": best_item})
        else:
            kept.append({**pair, "max_eval_similarity": round(best_sim, 4)})
    return kept, dropped


def write_report(
    out_dir: str | Path, kept: list[dict], dropped: list[dict], threshold: float
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Decontamination report",
        "",
        f"Threshold: cosine similarity {threshold} against every eval question and "
        "reference answer, embedded with the pinned local model.",
        "",
        f"Candidates: {len(kept) + len(dropped)}. Kept: {len(kept)}. Dropped: {len(dropped)}.",
        "",
    ]
    if dropped:
        lines.append("## Dropped pairs")
        lines.append("")
        for d in dropped:
            lines.append(f"- {d['pair_id']} ({d['kind']}): {d['similarity']} vs {d['nearest']}")
    else:
        lines.append("No candidate exceeded the threshold.")
    report = out_dir / "decontam_report.md"
    report.write_text("\n".join(lines) + "\n")
    (out_dir / "pairs.jsonl").write_text("".join(json.dumps(p) + "\n" for p in kept))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default="registry/candidate/pairs_raw.jsonl")
    parser.add_argument("--out", default="registry/candidate")
    parser.add_argument("--embedder", default="local", choices=["local", "fake"])
    args = parser.parse_args(argv)
    from corpusgate.retrieval.embed import get_embedder

    pairs = [json.loads(x) for x in Path(args.pairs).read_text().splitlines()]
    kept, dropped = decontaminate(pairs, get_embedder(args.embedder))
    report = write_report(args.out, kept, dropped, THRESHOLD)
    print(f"kept {len(kept)}, dropped {len(dropped)}; report at {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
