"""Mechanical retrieval metrics: hit rate and MRR against gold anchors.

These are computed from ranked retrieval lists with no judge involved,
so retrieval quality is reported independently of answer quality. A
retrieved chunk matches a gold anchor when its anchor prefix (the part
before the ordinal separator) equals the anchor: chunk IDs are minted
as DOCID#section-slug:ordinal from M2 onward, and at M1 the built-in
variants record bare anchors, which match as their own prefix.
"""

import json
from pathlib import Path

from corpusgate.evals.schema import load_questions


def anchor_of(chunk_id: str) -> str:
    """The anchor a chunk belongs to: everything before the ordinal separator."""
    return chunk_id.split(":", 1)[0]


def question_metrics(retrieved: list[str], gold_anchors: list[str], hit_at: int) -> dict:
    """Hit within the first hit_at results, and reciprocal rank of the first hit."""
    gold = set(gold_anchors)
    hit = any(anchor_of(c) in gold for c in retrieved[:hit_at])
    reciprocal_rank = 0.0
    for rank, chunk_id in enumerate(retrieved, start=1):
        if anchor_of(chunk_id) in gold:
            reciprocal_rank = 1.0 / rank
            break
    return {"hit": hit, "reciprocal_rank": reciprocal_rank}


def run_retrieval_metrics(
    run_dir: str | Path,
    questions_path: str | Path = "evalset/questions.jsonl",
    hit_at: int = 5,
) -> dict:
    """Aggregate hit rate and MRR over every non-refusal question in a run."""
    questions = {q["id"]: q for q in load_questions(questions_path)}
    run_dir = Path(run_dir)
    per_question = []
    for line in (run_dir / "records.jsonl").read_text().splitlines():
        record = json.loads(line)
        question = questions[record["question_id"]]
        if question["category"] == "refusal":
            continue
        m = question_metrics(record.get("retrieved", []), question["gold_anchors"], hit_at)
        per_question.append({"question_id": record["question_id"], **m})
    if not per_question:
        raise ValueError("no non-refusal records to score retrieval on")
    result = {
        "hit_at": hit_at,
        "n": len(per_question),
        "hit_rate": round(sum(m["hit"] for m in per_question) / len(per_question), 3),
        "mrr": round(
            sum(m["reciprocal_rank"] for m in per_question) / len(per_question), 3
        ),
    }
    (run_dir / "retrieval.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
