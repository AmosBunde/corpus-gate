"""Every query logs one record; aggregates come from the same file."""

import pytest
from fastapi.testclient import TestClient
from test_serve import FakeVariant, fake_lookup

from corpusgate.serve import metrics
from corpusgate.serve.app import create_app


@pytest.fixture()
def client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("CORPUSGATE_API_TOKEN", "secret-token")
    monkeypatch.setenv("SERVE_LOG", str(tmp_path / "requests.jsonl"))
    app = create_app()
    app.state.variant_factory = FakeVariant
    app.state.passage_lookup_factory = lambda: fake_lookup
    return TestClient(app)


def test_each_query_appends_one_record_and_metrics_aggregate(client: TestClient) -> None:
    headers = {"Authorization": "Bearer secret-token"}
    for _ in range(3):
        assert client.post("/query", json={"question": "?"}, headers=headers).status_code == 200
    body = client.get("/metrics", headers=headers).json()
    assert body["count"] == 3
    assert body["prompt_tokens"] == 300 and body["completion_tokens"] == 75
    assert body["refusal_share"] == 0.0 and body["mean_citations"] == 1.0
    assert body["p50_latency_ms"] >= 0


def test_metrics_requires_auth_and_empty_log_is_zero(client: TestClient) -> None:
    assert client.get("/metrics").status_code == 401
    headers = {"Authorization": "Bearer secret-token"}
    assert client.get("/metrics", headers=headers).json()["count"] == 0


def test_percentiles() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 100.0]
    assert metrics.percentile(values, 0.5) == 30.0
    assert metrics.percentile(values, 0.95) == 100.0
    assert metrics.percentile([], 0.5) == 0.0
