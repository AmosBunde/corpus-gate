"""The health endpoint answers and reports the configured backend."""

from fastapi.testclient import TestClient

from corpusgate.serve.app import app


def test_health_reports_status_and_backend() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_backend"] in {"local", "api"}
