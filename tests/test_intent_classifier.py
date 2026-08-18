from fastapi.testclient import TestClient

from src.services.intent_classifier.classifier import classifier_api

client = TestClient(classifier_api)


def test_healthz_returns_ok():
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
