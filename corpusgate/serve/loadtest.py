"""Load probe for the serving API: measured latency under stated conditions.

Fires a fixed number of queries at /query with bounded concurrency,
records client side wall latency per request, and then reads the
server side aggregates from /metrics so the two views can be compared.
The question set rotates through the smoke slice of the eval set, so
the probe exercises real retrieval against the real corpus rather
than a synthetic prompt.
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from corpusgate.serve.metrics import percentile


def load_smoke_questions(path: str | Path = "evalset/questions.jsonl") -> list[str]:
    questions = []
    for line in Path(path).read_text().splitlines():
        q = json.loads(line)
        if q.get("smoke"):
            questions.append(q["question"])
    return questions


def summarize(latencies_ms: list[float]) -> dict:
    ordered = sorted(latencies_ms)
    return {
        "count": len(ordered),
        "p50_ms": percentile(ordered, 0.5),
        "p95_ms": percentile(ordered, 0.95),
        "min_ms": ordered[0] if ordered else 0.0,
        "max_ms": ordered[-1] if ordered else 0.0,
    }


def run_load(url: str, token: str, questions: list[str], n: int, concurrency: int) -> dict:
    import httpx

    client = httpx.Client(timeout=1200)
    headers = {"Authorization": f"Bearer {token}"}

    def one(i: int) -> dict:
        question = questions[i % len(questions)]
        started = time.perf_counter()
        response = client.post(
            f"{url}/query", json={"question": question}, headers=headers
        )
        wall_ms = round((time.perf_counter() - started) * 1000, 1)
        body = response.json() if response.status_code == 200 else {}
        return {
            "status": response.status_code,
            "wall_ms": wall_ms,
            "prompt_tokens": body.get("prompt_tokens", 0),
            "completion_tokens": body.get("completion_tokens", 0),
        }

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(one, range(n)))

    ok = [r for r in results if r["status"] == 200]
    report = {
        "requests": n,
        "concurrency": concurrency,
        "succeeded": len(ok),
        "client": summarize([r["wall_ms"] for r in ok]),
        "prompt_tokens_total": sum(r["prompt_tokens"] for r in ok),
        "completion_tokens_total": sum(r["completion_tokens"] for r in ok),
    }
    server = client.get(f"{url}/metrics", headers=headers)
    if server.status_code == 200:
        report["server_metrics"] = server.json()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8001")
    parser.add_argument("--n", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    token = os.environ.get("CORPUSGATE_API_TOKEN", "")
    if not token:
        print("CORPUSGATE_API_TOKEN is required")
        return 1
    report = run_load(
        args.url, token, load_smoke_questions(), args.n, args.concurrency
    )
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
