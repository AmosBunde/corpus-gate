"""The RAG path is testable end to end with fakes: no model, no index, no network."""

import json

from corpusgate.evals import runner
from corpusgate.evals.rag import ANSWER_SCHEMA, BaseVariant, RagVariant


class FakeBackend:
    def __init__(self, payload: dict):
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str):
        self.prompts.append(prompt)
        return dict(self.payload), 120, 40


def fake_retriever(question: str) -> list[dict]:
    return [
        {"chunk_id": "DOC-A#section-1:0", "doc_id": "DOC-A", "section": "section-1",
         "text": "the governing law is Illinois", "score": 0.9},
        {"chunk_id": "DOC-A#section-2:0", "doc_id": "DOC-A", "section": "section-2",
         "text": "payment terms are net thirty", "score": 0.5},
    ]


def test_rag_cites_retrieved_and_drops_fabricated() -> None:
    backend = FakeBackend({
        "answer": "Illinois law governs.",
        "citations": [
            {"chunk_id": "DOC-A#section-1:0", "quote": "governing law is Illinois"},
            {"chunk_id": "DOC-FAKE#section-9:0", "quote": "invented"},
        ],
        "refused": False,
    })
    variant = RagVariant(retriever=fake_retriever, backend=backend)
    result = variant.answer({"question": "Which law governs?"})
    assert [c.chunk_id for c in result.citations] == ["DOC-A#section-1:0"]
    assert variant.dropped_citations == 1
    assert result.retrieved == ["DOC-A#section-1:0", "DOC-A#section-2:0"]
    assert result.prompt_tokens == 120 and result.completion_tokens == 40


def test_rag_prompt_carries_chunk_ids_and_question() -> None:
    backend = FakeBackend({"answer": "x", "citations": [], "refused": False})
    RagVariant(retriever=fake_retriever, backend=backend).answer({"question": "Which law?"})
    prompt = backend.prompts[0]
    assert "[DOC-A#section-1:0]" in prompt and "Which law?" in prompt
    assert "refuse" in prompt.lower()


def test_rag_refusal_passthrough() -> None:
    backend = FakeBackend({"answer": "Not in the corpus.", "citations": [], "refused": True})
    result = RagVariant(retriever=fake_retriever, backend=backend).answer({"question": "?"})
    assert result.refused is True and result.citations == []


def test_base_variant_never_retrieves_or_cites() -> None:
    backend = FakeBackend({
        "answer": "I have no corpus evidence.",
        "citations": [{"chunk_id": "SMUGGLED#x:0", "quote": "q"}],
        "refused": True,
    })
    result = BaseVariant(backend=backend).answer({"question": "?"})
    assert result.retrieved == [] and result.citations == []
    assert "no corpus" in backend.prompts[0]


def test_rag_runs_under_the_runner(tmp_path) -> None:
    backend = FakeBackend({"answer": "x", "citations": [], "refused": False})
    variant = RagVariant(retriever=fake_retriever, backend=backend)
    from corpusgate.evals import variants as vmod
    vmod.VARIANTS["fakerag"] = lambda: variant
    try:
        run_dir = runner.run_eval("fakerag", out_root=tmp_path, smoke_only=True)
    finally:
        del vmod.VARIANTS["fakerag"]
    records = [json.loads(x) for x in (run_dir / "records.jsonl").read_text().splitlines()]
    assert len(records) == 10
    assert all(r["retrieved"] == ["DOC-A#section-1:0", "DOC-A#section-2:0"] for r in records)


def test_answer_schema_shape() -> None:
    assert set(ANSWER_SCHEMA["required"]) == {"answer", "citations", "refused"}
