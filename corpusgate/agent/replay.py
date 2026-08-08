"""Replay a stored agent trace step by step, for review grounded in what happened.

Every scored agent answer is replayable: the runner persists one
trace per question under the run directory, and this CLI renders a
trace legibly so PR self-reviews and findings can cite steps rather
than impressions.
"""

import argparse
import json
import sys
from pathlib import Path


def render(trace: dict) -> str:
    lines = [f"trace for {trace.get('question_id', '?')}"]
    for step in trace["steps"]:
        forced = " (forced)" if step.get("forced") else ""
        tokens = f"{step['prompt_tokens']}+{step['completion_tokens']} tok"
        timing = f"[{step['latency_ms']} ms, {tokens}]"
        header = f"step {step['step']}: {step['action']}{forced}  {timing}"
        lines.append(header)
        if step.get("args"):
            lines.append(f"  args: {json.dumps(step['args'])}")
        if step.get("observed_chunk_ids"):
            lines.append(f"  observed: {', '.join(step['observed_chunk_ids'])}")
        if step.get("observation_digest"):
            digest = step["observation_digest"].replace("\n", "\n    ")
            lines.append(f"  observation:\n    {digest}")
    final = trace.get("final", {})
    lines.append(
        f"final: refused={final.get('refused')} citations={final.get('citations')} "
        f"dropped={final.get('dropped_citations')}"
    )
    lines.append(f"answer: {final.get('answer', '')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="run directory containing traces/")
    parser.add_argument("--question", default=None, help="question id; omit to list traces")
    args = parser.parse_args(argv)
    traces_dir = Path(args.run) / "traces"
    if not traces_dir.is_dir():
        print(f"no traces under {args.run}", file=sys.stderr)
        return 1
    if args.question is None:
        for path in sorted(traces_dir.glob("*.json")):
            trace = json.loads(path.read_text())
            steps = len(trace["steps"])
            refused = trace.get("final", {}).get("refused")
            print(f"{path.stem}: {steps} steps, refused={refused}")
        return 0
    path = traces_dir / f"{args.question}.json"
    if not path.exists():
        print(f"no trace for {args.question}", file=sys.stderr)
        return 1
    print(render(json.loads(path.read_text())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
