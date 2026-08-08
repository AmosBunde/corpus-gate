"""The gate: promote or reject a candidate against the champion, per the config.

The rule comes from configs/eval.yaml and is not negotiable at run
time: overall must exceed the champion, and no category may drop
beyond the tolerance. Promotion is explicit: with --promote the
candidate's scored artifacts copy into runs/promoted/ (the one
corner of runs/ under version control) and the champion pointer in
the config moves. Rejections print their reasons; nothing is
deleted, and the finding documents the rejected variant.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

from corpusgate.evals.judge import category_means
from corpusgate.evals.schema import CATEGORIES

CONFIG_PATH = "configs/eval.yaml"


def verdict(candidate_run: str | Path, champion_run: str | Path | None, config: dict) -> dict:
    candidate = category_means(candidate_run)
    if champion_run is None:
        return {
            "verdict": "promote",
            "reasons": ["no champion exists; the first scored candidate takes the title"],
            "candidate": candidate,
            "champion": None,
            "deltas": None,
        }
    champion = category_means(champion_run)
    tolerance = config["gate"]["category_tolerance"]
    reasons = []
    deltas = {}
    for category in (*CATEGORIES, "overall"):
        deltas[category] = round(candidate[category] - champion[category], 1)
    if config["gate"]["require_overall_gain"] and candidate["overall"] <= champion["overall"]:
        reasons.append(
            f"overall must rise: candidate {candidate['overall']} vs champion "
            f"{champion['overall']}"
        )
    for category in CATEGORIES:
        drop = champion[category] - candidate[category]
        if drop > tolerance:
            reasons.append(
                f"{category} drops {round(drop, 1)} beyond tolerance {tolerance}"
            )
    return {
        "verdict": "reject" if reasons else "promote",
        "reasons": reasons or ["overall rose and every category held within tolerance"],
        "candidate": candidate,
        "champion": champion,
        "deltas": deltas,
    }


def promote_run(candidate_run: str | Path, config_path: str | Path = CONFIG_PATH) -> Path:
    """Copy the scored artifacts into runs/promoted/ and move the champion pointer."""
    candidate_run = Path(candidate_run)
    promoted_dir = Path("runs/promoted") / candidate_run.name
    promoted_dir.mkdir(parents=True, exist_ok=True)
    for name in ("run.json", "scores.jsonl", "judge.json", "retrieval.json"):
        source = candidate_run / name
        if source.exists():
            shutil.copy2(source, promoted_dir / name)
    config_text = Path(config_path).read_text()
    config = yaml.safe_load(config_text)
    previous = config["gate"]["champion"]
    updated = config_text.replace(
        f"champion: {previous if previous is not None else 'null'}",
        f"champion: {promoted_dir}",
        1,
    )
    Path(config_path).write_text(updated)
    return promoted_dir


def render_verdict(result: dict) -> str:
    lines = [f"gate verdict: {result['verdict'].upper()}"]
    for reason in result["reasons"]:
        lines.append(f"  - {reason}")
    if result["deltas"]:
        lines.append("  deltas vs champion: " + json.dumps(result["deltas"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True, help="scored candidate run directory")
    parser.add_argument("--config", default=CONFIG_PATH)
    parser.add_argument("--promote", action="store_true",
                        help="on a promote verdict, move the champion pointer")
    args = parser.parse_args(argv)
    config = yaml.safe_load(Path(args.config).read_text())
    champion_run = config["gate"]["champion"]
    result = verdict(args.candidate, champion_run, config)
    print(render_verdict(result))
    if result["verdict"] == "promote" and args.promote:
        promoted = promote_run(args.candidate, args.config)
        print(f"champion is now {promoted}")
    elif result["verdict"] == "promote":
        print("run again with --promote to move the champion pointer")
    return 0 if result["verdict"] == "promote" else 1


if __name__ == "__main__":
    sys.exit(main())
