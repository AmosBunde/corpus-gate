"""The loop is bounded, forced, and structurally honest, proven with a scripted backend."""

import json
from pathlib import Path

import pytest

from corpusgate.agent.loop import MAX_STEPS, AgentVariant
from corpusgate.agent.tools import Toolbox
from corpusgate.retrieval import index
from corpusgate.retrieval.embed import FakeEmbedder

CHUNKS = [
    {"chunk_id": "DOC-A#section-1:0", "doc_id": "DOC-A", "section": "section-1",
     "doc_title": "ALPHA", "text": "the governing law is Illinois"},
    {"chunk_id": "DOC-B#section-1:0", "doc_id": "DOC-B", "section": "section-1",
     "doc_title": "BETA", "text": "the governing law is Nevada"},
]


class ScriptedBackend:
    def __init__(self, steps: list[dict]):
        self._steps = list(steps)
        self.prompts: list[str] = []

    def complete(self, prompt: str, schema: dict | None = None):
        self.prompts.append(prompt)
        return self._steps.pop(0), 100, 30


@pytest.fixture()
def toolbox(tmp_path: Path) -> Toolbox:
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text("".join(json.dumps(c) + "\n" for c in CHUNKS))
    client = index.get_client(":memory:")
    embedder = FakeEmbedder()
    index.load_chunks(client, embedder, chunks_path)
    return Toolbox(client, embedder, tmp_path)


def _step(action: str, **kw) -> dict:
    base = {"action": action, "query": None, "doc_id": None, "section": None,
            "doc_ids": None, "answer": None, "citations": None, "refused": None}
    base.update(kw)
    return base


def test_two_step_episode_cites_observed(toolbox: Toolbox) -> None:
    backend = ScriptedBackend([
        _step("search_corpus", query="governing law"),
        _step("answer", answer="Illinois governs.", refused=False,
              citations=[{"chunk_id": "DOC-A#section-1:0", "quote": "Illinois"},
                         {"chunk_id": "DOC-Z#fake:0", "quote": "invented"}]),
    ])
    variant = AgentVariant(toolbox=toolbox, backend=backend)
    result = variant.answer({"id": "q-001", "question": "Which law governs?"})
    assert [c.chunk_id for c in result.citations] == ["DOC-A#section-1:0"]
    assert variant.dropped_citations == 1
    assert "DOC-A#section-1:0" in result.retrieved
    assert result.prompt_tokens == 200 and result.completion_tokens == 60
    trace = variant.traces["q-001"]
    assert [s["action"] for s in trace["steps"]] == ["search_corpus", "answer"]
    assert trace["final"]["dropped_citations"] == 1


def test_budget_forces_answer_at_step_six(toolbox: Toolbox) -> None:
    backend = ScriptedBackend(
        [_step("search_corpus", query=f"attempt {i}") for i in range(MAX_STEPS - 1)]
        + [{"answer": "Forced.", "citations": [], "refused": True}]
    )
    variant = AgentVariant(toolbox=toolbox, backend=backend)
    result = variant.answer({"id": "q-002", "question": "?"})
    trace = variant.traces["q-002"]
    assert len(trace["steps"]) == MAX_STEPS
    assert trace["steps"][-1]["forced"] is True
    assert result.refused is True
    assert "budget is exhausted" in backend.prompts[-1]


def test_unknown_action_becomes_observation_and_loop_continues(toolbox: Toolbox) -> None:
    backend = ScriptedBackend([
        _step("read_document", doc_id="DOC-MISSING"),
        _step("answer", answer="Cannot find it.", citations=[], refused=True),
    ])
    variant = AgentVariant(toolbox=toolbox, backend=backend)
    result = variant.answer({"id": "q-003", "question": "?"})
    assert result.refused is True
    assert "unknown doc_id" in backend.prompts[1]


def test_cross_reference_grows_citable_set(toolbox: Toolbox) -> None:
    backend = ScriptedBackend([
        _step("cross_reference", query="governing law", doc_ids=["DOC-A", "DOC-B"]),
        _step("answer", answer="Illinois versus Nevada.", refused=False,
              citations=[{"chunk_id": "DOC-A#section-1:0", "quote": "Illinois"},
                         {"chunk_id": "DOC-B#section-1:0", "quote": "Nevada"}]),
    ])
    result = AgentVariant(toolbox=toolbox, backend=backend).answer({"id": "q-004", "question": "?"})
    assert {c.chunk_id for c in result.citations} == {"DOC-A#section-1:0", "DOC-B#section-1:0"}


def test_step_prompt_counts_down_and_names_tools(toolbox: Toolbox) -> None:
    backend = ScriptedBackend([
        _step("search_corpus", query="x"),
        _step("answer", answer="a", citations=[], refused=False),
    ])
    AgentVariant(toolbox=toolbox, backend=backend).answer({"id": "q-005", "question": "?"})
    first, second = backend.prompts
    assert "6 of 6 steps" in first and "5 of 6 steps" in second
    assert "search_corpus" in first and "cross_reference" in first
    assert "step 1 search_corpus result" in second
