"""The scoreboard: one table over any set of scored runs.

Renders the README section 11 shape: per-category scores, overall,
retrieval metrics, latency, and token cost, one row per run. This is
the artifact the gate reads at M4 and the source for the canonical
results table; it never decides anything itself.
"""

import argparse
import json
import sys
from pathlib import Path

from corpusgate.evals.judge import category_means
from corpusgate.evals.schema import CATEGORIES

COLUMNS = ["variant", *CATEGORIES, "overall", "hit_rate", "mrr", "p50_ms", "tokens"]


def p50(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0.0


def run_row(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "run.json").read_text())
    means = category_means(run_dir)
    retrieval = {}
    if (run_dir / "retrieval.json").exists():
        retrieval = json.loads((run_dir / "retrieval.json").read_text())
    records = [json.loads(x) for x in (run_dir / "records.jsonl").read_text().splitlines()]
    tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in records)
    return {
        "variant": meta["variant"],
        **{c: means.get(c, 0.0) for c in CATEGORIES},
        "overall": means["overall"],
        "hit_rate": retrieval.get("hit_rate", ""),
        "mrr": retrieval.get("mrr", ""),
        "p50_ms": round(p50([r["latency_ms"] for r in records]), 1),
        "tokens": tokens,
    }


def render(rows: list[dict]) -> str:
    header = "| " + " | ".join(COLUMNS) + " |"
    divider = "|" + "|".join(" --- " for _ in COLUMNS) + "|"
    lines = [header, divider]
    for row in rows:
        lines.append("| " + " | ".join(str(row[c]) for c in COLUMNS) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="*", default=None, help="run dirs; default: all scored")
    parser.add_argument("--out", default=None, help="also write the table to this file")
    args = parser.parse_args(argv)
    run_dirs = [Path(r) for r in args.runs] if args.runs else sorted(
        p for p in Path("runs").iterdir() if (p / "scores.jsonl").exists()
    )
    if not run_dirs:
        print("no scored runs found", file=sys.stderr)
        return 1
    table = render([run_row(r) for r in run_dirs])
    print(table)
    if args.out:
        Path(args.out).write_text(table + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
