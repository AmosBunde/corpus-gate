"""The eval runner: drives any variant over the question set and records everything.

One run produces one directory under runs/ holding run.json (what ran,
against which questions, when) and records.jsonl (one record per
question: the answer payload, latency, and token usage). Scoring is a
separate pass over the records, so answers are collected once and can
be re-judged without re-running the variant.
"""

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from corpusgate.evals.schema import load_questions
from corpusgate.evals.variants import get_variant


def run_eval(
    variant_name: str,
    questions_path: str | Path = "evalset/questions.jsonl",
    out_root: str | Path = "runs",
    smoke_only: bool = False,
) -> Path:
    """Answer every selected question with the variant; returns the run directory."""
    variant = get_variant(variant_name)
    questions = load_questions(questions_path)
    if smoke_only:
        questions = [q for q in questions if q["smoke"]]
    if not questions:
        raise ValueError("no questions selected")

    started = datetime.now(UTC)
    run_dir = Path(out_root) / f"{variant_name}-{started.strftime('%Y%m%dT%H%M%SZ')}"
    run_dir.mkdir(parents=True, exist_ok=False)

    records = []
    for q in questions:
        t0 = time.perf_counter()
        result = variant.answer(q)
        latency_ms = round((time.perf_counter() - t0) * 1000, 3)
        records.append(
            {
                "question_id": q["id"],
                "category": q["category"],
                "smoke": q["smoke"],
                "answer": result.answer,
                "citations": [asdict(c) for c in result.citations],
                "refused": result.refused,
                "latency_ms": latency_ms,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            }
        )

    with open(run_dir / "records.jsonl", "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    run_meta = {
        "variant": variant_name,
        "started_at": started.isoformat(),
        "smoke_only": smoke_only,
        "question_count": len(records),
        "questions_sha256": hashlib.sha256(Path(questions_path).read_bytes()).hexdigest(),
        "total_latency_ms": round(sum(r["latency_ms"] for r in records), 3),
    }
    (run_dir / "run.json").write_text(json.dumps(run_meta, indent=2) + "\n")
    return run_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--questions", default="evalset/questions.jsonl")
    parser.add_argument("--out", default="runs")
    parser.add_argument("--smoke", action="store_true", help="run only the smoke slice")
    args = parser.parse_args(argv)
    run_dir = run_eval(args.variant, args.questions, args.out, smoke_only=args.smoke)
    meta = json.loads((run_dir / "run.json").read_text())
    print(f"{meta['question_count']} answers recorded in {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
