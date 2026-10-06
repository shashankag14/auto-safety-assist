from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.services.response_generator import generator
from src.services.response_generator.generator import generator_api

client = TestClient(generator_api)


def test_healthz_returns_ok():
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_answer_uses_general_instructions(monkeypatch):
    calls = {}

    def fake_create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(output_text="A recall is ...")

    monkeypatch.setattr(generator.client.responses, "create", fake_create)

    response = client.post("/answer", json={"query": "what does a recall actually mean?"})

    assert response.status_code == 200
    assert response.json() == {"response": "A recall is ..."}
    assert calls["instructions"] == generator.cfg.general_instructions
    assert calls["input"] == "what does a recall actually mean?"
