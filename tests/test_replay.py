"""Traces persist with runs and replay legibly."""

import json

from corpusgate.agent.replay import render
from corpusgate.evals import runner
from corpusgate.evals.variants import VariantAnswer

TRACE = {
    "question_id": "q-001",
    "steps": [
        {"step": 1, "action": "search_corpus", "args": {"query": "law"},
         "observation_digest": "[D#s:0] the law", "observed_chunk_ids": ["D#s:0"],
         "latency_ms": 12.0, "prompt_tokens": 100, "completion_tokens": 20},
        {"step": 2, "action": "answer", "forced": False,
         "latency_ms": 9.0, "prompt_tokens": 120, "completion_tokens": 30},
    ],
    "final": {"answer": "The law governs.", "refused": False,
              "citations": ["D#s:0"], "dropped_citations": 0},
}


class TracingVariant:
    name = "tracer"

    def __init__(self):
        self.traces = {}

    def answer(self, question):
        self.traces[question["id"]] = {**TRACE, "question_id": question["id"]}
        return VariantAnswer(answer="x", refused=False)


def test_runner_persists_traces(tmp_path) -> None:
    from corpusgate.evals import variants as vmod
    vmod.VARIANTS["tracer"] = TracingVariant
    try:
        run_dir = runner.run_eval("tracer", out_root=tmp_path, smoke_only=True)
    finally:
        del vmod.VARIANTS["tracer"]
    traces = sorted((run_dir / "traces").glob("*.json"))
    assert len(traces) == 10
    stored = json.loads(traces[0].read_text())
    assert stored["steps"][0]["action"] == "search_corpus"


def test_render_shows_steps_and_final() -> None:
    text = render(TRACE)
    assert "step 1: search_corpus" in text
    assert '"query": "law"' in text
    assert "observed: D#s:0" in text
    assert "final: refused=False" in text
    assert "The law governs." in text
