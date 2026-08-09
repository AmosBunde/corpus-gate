"""The serving API: open health, enforced auth, passage-enriched answers."""

import json

import pytest
from fastapi.testclient import TestClient

from corpusgate.evals.variants import Citation, VariantAnswer
from corpusgate.serve.app import create_app


class FakeVariant:
    name = "fake"

    def answer(self, question):
        return VariantAnswer(
            answer="Illinois law governs.",
            citations=[Citation(chunk_id="DOC-A#section-1:0", quote="Illinois")],
            refused=False,
            retrieved=["DOC-A#section-1:0"],
            prompt_tokens=100,
            completion_tokens=25,
        )


def fake_lookup(chunk_ids):
    return {
        "DOC-A#section-1:0": {
            "chunk_id": "DOC-A#section-1:0",
            "doc_id": "DOC-A",
            "section": "section-1",
            "text": "the governing law is Illinois",
        }
    }


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("CORPUSGATE_API_TOKEN", "secret-token")
    app = create_app()
    app.state.variant_factory = FakeVariant
    app.state.passage_lookup_factory = lambda: fake_lookup
    return TestClient(app)


def test_health_is_open_and_versioned(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_backend"] in {"local", "api"}


def test_query_requires_bearer_token(client: TestClient) -> None:
    assert client.post("/query", json={"question": "?"}).status_code == 401
    wrong = client.post(
        "/query", json={"question": "?"}, headers={"Authorization": "Bearer nope"}
    )
    assert wrong.status_code == 401


def test_unconfigured_token_is_a_server_error(monkeypatch) -> None:
    monkeypatch.delenv("CORPUSGATE_API_TOKEN", raising=False)
    app = create_app()
    app.state.variant_factory = FakeVariant
    app.state.passage_lookup_factory = lambda: fake_lookup
    response = TestClient(app).post("/query", json={"question": "?"})
    assert response.status_code == 503


def test_query_returns_enriched_citations_and_accounting(client: TestClient) -> None:
    response = client.post(
        "/query",
        json={"question": "Which law governs?"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Illinois law governs."
    citation = body["citations"][0]
    assert citation["passage"] == "the governing law is Illinois"
    assert citation["doc_id"] == "DOC-A" and citation["section"] == "section-1"
    assert body["prompt_tokens"] == 100 and body["completion_tokens"] == 25
    assert body["latency_ms"] >= 0 and body["request_id"]


def test_stream_emits_status_then_answer(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/query/stream",
        json={"question": "?"},
        headers={"Authorization": "Bearer secret-token"},
    ) as response:
        payload = "".join(response.iter_text())
    assert "event: status" in payload
    assert "event: answer" in payload
    answer_line = [x for x in payload.splitlines() if x.startswith("data: {")][0]
    assert json.loads(answer_line[len("data: "):])["answer"] == "Illinois law governs."
