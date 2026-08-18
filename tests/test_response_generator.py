from fastapi.testclient import TestClient

from src.services.response_generator.generator import generator_api

client = TestClient(generator_api)


def test_healthz_returns_ok():
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
