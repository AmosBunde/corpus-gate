"""The pinned judge: rubric scoring over run records, plus the human-audit protocol.

Scoring is a separate pass over a run directory written by the runner,
so a re-judge never re-runs a variant. The judge model, prompt version,
and audit parameters are pinned in configs/judge.yaml and recorded in
every score file; two runs are comparable only when those pins match.

Determinism note: the pinned model (claude-sonnet-5) rejects sampling
parameters, so there is no temperature to set. Determinism comes from
the pinned prompt, disabled thinking, and a structured-output schema
that forces valid JSON verdicts.

The human audit is a protocol, not an intention: every scored run gets
a deterministic 15-question subsample written as a blind scoring sheet
(no judge scores on it, to avoid anchoring), and the agreement command
computes mean absolute difference and pass/fail agreement once the
sheet is filled in.
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import yaml

from corpusgate.evals.schema import load_questions

CONFIG_PATH = "configs/judge.yaml"

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria_met": {
            "type": "array",
            "items": {"type": "boolean"},
            "description": "One verdict per rubric criterion, in order",
        },
        "score": {"type": "integer", "description": "Overall 0 to 100"},
        "rationale": {"type": "string"},
    },
    "required": ["criteria_met", "score", "rationale"],
    "additionalProperties": False,
}

PROMPT_V1 = """You are the eval judge for CorpusGate, a corpus question answering system.
Grade the candidate answer against the rubric, strictly and independently per criterion.

Question ({category}): {question}

Rubric criteria:
{rubric_lines}

Reference answer: {reference_answer}

Candidate answer: {answer}
Candidate citations (chunk ids): {citations}
Candidate refused: {refused}

Scoring rules:
- Grade each rubric criterion true or false, in order.
- score is 0 to 100 overall: weight rubric coverage, correctness of figures and
  qualifiers, and citation correctness.
- A fabricated figure, date, or source scores 0 regardless of other criteria.
- For refusal category questions, a fluent answer with an invented figure is the
  worst outcome and scores 0; a correct refusal with the right reason scores high.
- For non-refusal questions, an unsupported refusal scores 0.
- An uncited claim that the rubric requires a citation for fails that criterion.

Respond with JSON only: criteria_met (one boolean per rubric criterion, in order),
score (integer 0 to 100), rationale (one or two sentences)."""


def load_config(path: str | Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text())


def build_prompt(question: dict, record: dict, prompt_version: int = 1) -> str:
    if prompt_version != 1:
        raise ValueError(f"unknown judge prompt version {prompt_version}")
    rubric_lines = "\n".join(f"{i}. {c}" for i, c in enumerate(question["rubric"], start=1))
    citations = ", ".join(c["chunk_id"] for c in record["citations"]) or "none"
    return PROMPT_V1.format(
        category=question["category"],
        question=question["question"],
        rubric_lines=rubric_lines,
        reference_answer=question["reference_answer"],
        answer=record["answer"],
        citations=citations,
        refused=record["refused"],
    )


class AnthropicJudgeBackend:
    """The pinned judge over the Anthropic API, structured outputs enforced."""

    name = "api"

    def __init__(self, model: str, max_tokens: int, prompt_version: int):
        import anthropic  # lazy: only the api backend needs the SDK or a key

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        self._prompt_version = prompt_version

    def judge(self, question: dict, record: dict) -> dict:
        prompt = build_prompt(question, record, self._prompt_version)
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            raise RuntimeError(f"judge declined to grade {question['id']}")
        text = next(block.text for block in response.content if block.type == "text")
        return json.loads(text)


class MockJudgeBackend:
    """Deterministic stand-in for tests and CI; never touches the network.

    Scoring is intentionally crude: exact reference match with correct
    refusal behavior scores 100, wrong refusal behavior scores 0, and
    anything else scores 25. That is enough to bracket the harness:
    the oracle variant must score 100 everywhere and the echo variant
    must score 100 only on refusal questions.
    """

    name = "mock"

    def judge(self, question: dict, record: dict) -> dict:
        n = len(question["rubric"])
        should_refuse = question["category"] == "refusal"
        if record["refused"] != should_refuse:
            return {"criteria_met": [False] * n, "score": 0, "rationale": "refusal mismatch"}
        if should_refuse or record["answer"] == question["reference_answer"]:
            return {"criteria_met": [True] * n, "score": 100, "rationale": "matches reference"}
        return {"criteria_met": [False] * n, "score": 25, "rationale": "differs from reference"}


def get_backend(config: dict, override: str | None = None):
    judge_cfg = config["judge"]
    backend = override or judge_cfg["backend"]
    if backend == "api":
        return AnthropicJudgeBackend(
            judge_cfg["model"], judge_cfg["max_tokens"], judge_cfg["prompt_version"]
        )
    if backend == "mock":
        return MockJudgeBackend()
    raise ValueError(f"unknown judge backend {backend!r}")


def normalize_verdict(verdict: dict, rubric_len: int) -> dict:
    """Clamp the score and force criteria_met to rubric length; judges drift."""
    score = max(0, min(100, int(verdict["score"])))
    criteria = [bool(c) for c in verdict["criteria_met"]][:rubric_len]
    criteria += [False] * (rubric_len - len(criteria))
    return {"criteria_met": criteria, "score": score, "rationale": str(verdict["rationale"])}


def resolve_run_dir(run: str, out_root: str | Path = "runs") -> Path:
    if run != "latest":
        return Path(run)
    candidates = sorted(
        (p for p in Path(out_root).iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError("no runs found under runs/")
    return candidates[-1]


def audit_sample_ids(run_meta: dict, question_ids: list[str], size: int) -> list[str]:
    """Deterministic blind subsample: same run inputs, same sample, forever."""
    seed_material = f"{run_meta['questions_sha256']}:{run_meta['variant']}"
    seed = int(hashlib.sha256(seed_material.encode()).hexdigest(), 16)
    rng = random.Random(seed)
    return sorted(rng.sample(sorted(question_ids), min(size, len(question_ids))))


def score_run(
    run_dir: str | Path,
    questions_path: str | Path = "evalset/questions.jsonl",
    config_path: str | Path = CONFIG_PATH,
    backend_override: str | None = None,
) -> Path:
    run_dir = Path(run_dir)
    config = load_config(config_path)
    backend = get_backend(config, backend_override)
    questions = {q["id"]: q for q in load_questions(questions_path)}
    records = [
        json.loads(line) for line in (run_dir / "records.jsonl").read_text().splitlines()
    ]
    run_meta = json.loads((run_dir / "run.json").read_text())

    scores = []
    for record in records:
        question = questions[record["question_id"]]
        verdict = normalize_verdict(backend.judge(question, record), len(question["rubric"]))
        scores.append(
            {
                "question_id": record["question_id"],
                "category": record["category"],
                **verdict,
            }
        )
    with open(run_dir / "scores.jsonl", "w") as f:
        for s in scores:
            f.write(json.dumps(s) + "\n")

    judge_cfg = config["judge"]
    (run_dir / "judge.json").write_text(
        json.dumps(
            {
                "backend": backend.name,
                "model": judge_cfg["model"],
                "prompt_version": judge_cfg["prompt_version"],
                "scored": len(scores),
            },
            indent=2,
        )
        + "\n"
    )

    audit_size = config["human_audit"]["subsample_size"]
    sample = set(audit_sample_ids(run_meta, [s["question_id"] for s in scores], audit_size))
    by_id = {r["question_id"]: r for r in records}
    with open(run_dir / "human_audit_sheet.jsonl", "w") as f:
        for qid in sorted(sample):
            q = questions[qid]
            f.write(
                json.dumps(
                    {
                        "question_id": qid,
                        "category": q["category"],
                        "question": q["question"],
                        "rubric": q["rubric"],
                        "reference_answer": q["reference_answer"],
                        "candidate_answer": by_id[qid]["answer"],
                        "candidate_refused": by_id[qid]["refused"],
                        "human_score": None,
                    }
                )
                + "\n"
            )
    return run_dir


def compute_agreement(run_dir: str | Path, config_path: str | Path = CONFIG_PATH) -> dict:
    """Judge-human agreement once the audit sheet is filled in by a person."""
    run_dir = Path(run_dir)
    threshold = load_config(config_path)["human_audit"]["pass_threshold"]
    judge_scores = {
        row["question_id"]: row["score"]
        for row in map(json.loads, (run_dir / "scores.jsonl").read_text().splitlines())
    }
    pairs = []
    for row in map(json.loads, (run_dir / "human_audit_sheet.jsonl").read_text().splitlines()):
        if row["human_score"] is None:
            continue
        pairs.append((judge_scores[row["question_id"]], int(row["human_score"])))
    if not pairs:
        raise ValueError("no human scores filled in on the audit sheet")
    mad = sum(abs(j - h) for j, h in pairs) / len(pairs)
    agree = sum((j >= threshold) == (h >= threshold) for j, h in pairs) / len(pairs)
    result = {
        "n": len(pairs),
        "mean_absolute_difference": round(mad, 2),
        "pass_fail_agreement": round(agree, 3),
        "pass_threshold": threshold,
    }
    (run_dir / "agreement.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def category_means(run_dir: str | Path) -> dict:
    totals: dict[str, list[int]] = {}
    for row in map(json.loads, (Path(run_dir) / "scores.jsonl").read_text().splitlines()):
        totals.setdefault(row["category"], []).append(row["score"])
    means = {cat: round(sum(v) / len(v), 1) for cat, v in sorted(totals.items())}
    all_scores = [s for v in totals.values() for s in v]
    means["overall"] = round(sum(all_scores) / len(all_scores), 1)
    return means


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_score = sub.add_parser("score", help="judge every record in a run")
    p_score.add_argument("--run", default="latest")
    p_score.add_argument("--questions", default="evalset/questions.jsonl")
    p_score.add_argument("--backend", default=None, help="override configs/judge.yaml backend")
    p_agree = sub.add_parser("agreement", help="compute judge-human agreement for a run")
    p_agree.add_argument("--run", default="latest")
    args = parser.parse_args(argv)

    run_dir = resolve_run_dir(args.run)
    if args.command == "score":
        score_run(run_dir, args.questions, backend_override=args.backend)
        means = category_means(run_dir)
        print(f"scored {run_dir}: " + ", ".join(f"{k}={v}" for k, v in means.items()))
        print(f"blind audit sheet written to {run_dir}/human_audit_sheet.jsonl")
    else:
        result = compute_agreement(run_dir)
        print(f"agreement over {result['n']} questions: " + json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
