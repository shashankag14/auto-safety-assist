from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.services.intent_classifier import classifier
from src.services.intent_classifier.classifier import classifier_api
from src.services.intent_classifier.schemas import Intent, IntentOutput

client = TestClient(classifier_api)


def test_healthz_returns_ok():
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_classify_returns_parsed_intent(monkeypatch):
    monkeypatch.setattr(classifier.client.responses, "parse",
                        lambda **_: SimpleNamespace(output_parsed=IntentOutput(intent=Intent.RECALL_LOOKUP)))

    response = client.post("/classify", json={"query": "is there a recall on my 2018 bmw x5"})

    assert response.status_code == 200
    assert response.json() == {"intent": "recall_lookup"}


def test_classify_returns_null_intent_when_output_unparsed(monkeypatch):
    monkeypatch.setattr(classifier.client.responses, "parse", lambda **_: SimpleNamespace(output_parsed=None))

    response = client.post("/classify", json={"query": "is there a recall on my 2018 bmw x5"})

    assert response.status_code == 200
    assert response.json() == {"intent": None}
