"""Per-request accounting: one JSONL record per query, aggregates on demand.

Latency and token cost are logged per request and queryable, per the
contract. The log is plain JSONL so anything can consume it; the
aggregates endpoint computes count, latency percentiles, token
totals, and refusal share from the same file it writes, so there is
exactly one source of truth for cost claims.
"""

import json
import os
from pathlib import Path

DEFAULT_LOG = "serve_logs/requests.jsonl"


def log_path() -> Path:
    return Path(os.environ.get("SERVE_LOG", DEFAULT_LOG))


def append_record(record: dict, path: str | Path | None = None) -> None:
    path = Path(path or log_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[idx]


def aggregate(path: str | Path | None = None) -> dict:
    path = Path(path or log_path())
    if not path.exists():
        return {"count": 0}
    records = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    if not records:
        return {"count": 0}
    latencies = [r["latency_ms"] for r in records]
    return {
        "count": len(records),
        "p50_latency_ms": round(percentile(latencies, 0.50), 1),
        "p95_latency_ms": round(percentile(latencies, 0.95), 1),
        "prompt_tokens": sum(r["prompt_tokens"] for r in records),
        "completion_tokens": sum(r["completion_tokens"] for r in records),
        "refusal_share": round(sum(r["refused"] for r in records) / len(records), 3),
        "mean_citations": round(
            sum(r["citations"] for r in records) / len(records), 2
        ),
    }
