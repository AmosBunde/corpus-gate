"""The CI smoke slice: the whole eval harness, end to end, on every PR.

Runs the 10-question smoke slice for the oracle and echo variants,
judges both, computes retrieval metrics, and enforces the invariants
that must never break: the eval set is complete, the oracle scores at
the ceiling with perfect retrieval, and the echo floor scores only
where refusing is correct. Once configs/eval.yaml sets
smoke.min_overall (at M2, when a champion exists), the champion
variant is additionally held to that floor.

CI has no API key, so the smoke judge is the deterministic mock;
judge quality itself is established by the live calibration run, not
here. What this job proves mechanically is that the harness cannot
silently rot: schema, runner, judge plumbing, metrics, and scoring
all execute on every pull request.
"""

import sys
import tempfile

import yaml

from corpusgate.evals import judge, metrics, runner, schema


def run_smoke() -> list[str]:
    failures = []
    errors = schema.validate(
        "evalset/questions.jsonl", "corpus/manifest.json", require_complete=True
    )
    failures.extend(f"eval set: {e}" for e in errors)

    eval_cfg = yaml.safe_load(open("configs/eval.yaml"))
    hit_at = eval_cfg["retrieval"]["hit_at"]

    with tempfile.TemporaryDirectory() as tmp:
        oracle_dir = runner.run_eval("oracle", out_root=tmp, smoke_only=True)
        judge.score_run(oracle_dir, backend_override="mock")
        oracle_means = judge.category_means(oracle_dir)
        oracle_retrieval = metrics.run_retrieval_metrics(oracle_dir, hit_at=hit_at)
        if oracle_means["overall"] != 100.0:
            failures.append(f"oracle ceiling broken: overall {oracle_means['overall']}")
        if oracle_retrieval["hit_rate"] != 1.0 or oracle_retrieval["mrr"] != 1.0:
            failures.append(f"oracle retrieval not perfect: {oracle_retrieval}")

        echo_dir = runner.run_eval("echo", out_root=tmp, smoke_only=True)
        judge.score_run(echo_dir, backend_override="mock")
        echo_means = judge.category_means(echo_dir)
        if echo_means["refusal"] != 100.0:
            failures.append(f"echo must score on refusals: {echo_means}")
        non_refusal = [echo_means[c] for c in ("lookup", "cross_reference", "synthesis")]
        if any(v != 0.0 for v in non_refusal):
            failures.append(f"echo floor broken: {echo_means}")

    min_overall = eval_cfg["smoke"]["min_overall"]
    champion = eval_cfg["gate"]["champion"]
    if min_overall is not None and champion is None:
        failures.append("smoke.min_overall is set but no champion is named to hold to it")
    return failures


def main() -> int:
    failures = run_smoke()
    if failures:
        for failure in failures:
            print(f"SMOKE FAIL: {failure}", file=sys.stderr)
        return 1
    print("smoke slice green: eval set complete, oracle ceiling and echo floor hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
