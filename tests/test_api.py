from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from noc_copilot.config import load_settings
from noc_copilot.pipeline import Result

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    # The startup event does not fire because TestClient is not entered as a
    # context manager, so app.state is populated here instead: a patched
    # Pipeline, fresh rate-limit counters, and real settings (the session-cap
    # test mutates settings.session_cap).
    with patch("noc_copilot.api.Pipeline") as PipelineMock:
        from noc_copilot import api

        api.app.state.pipeline = PipelineMock.return_value
        api.app.state.settings = load_settings(REPO / "config" / "settings.yaml")
        api.app.state.used = {}
        api.app.state.total = 0
        yield TestClient(api.app), PipelineMock.return_value


def test_chat_returns_an_answer(client):
    test_client, pipeline = client
    pipeline.answer.return_value = Result(
        answer="T310 starts on physical layer problems.", refused=False,
        citations=[{"clause_id": "5.3.5.3", "citation": "TS 38.331 v17.5.0 §5.3.5.3",
                    "supporting_quote": "q", "text": "t"}],
        model_id="g", latency_ms=120)
    response = test_client.post("/chat", json={"question": "When does T310 start?",
                                               "session_id": "s1"})
    assert response.status_code == 200
    assert response.json()["refused"] is False
    assert response.json()["citations"][0]["citation"] == "TS 38.331 v17.5.0 §5.3.5.3"


def test_chat_reports_a_refusal_with_its_reason(client):
    test_client, pipeline = client
    pipeline.answer.return_value = Result(answer="No clause covers this.", refused=True,
                                          refusal_reason="no_relevant_clause",
                                          gate="relevance", latency_ms=5)
    body = test_client.post("/chat", json={"question": "Wi-Fi 7?", "session_id": "s1"}).json()
    assert body["refused"] is True and body["refusal_reason"] == "no_relevant_clause"


def test_session_cap_is_enforced(client):
    test_client, pipeline = client
    pipeline.answer.return_value = Result(answer="a", refused=False)
    from noc_copilot import api
    api.app.state.settings.session_cap = 2
    for _ in range(2):
        assert test_client.post("/chat", json={"question": "q", "session_id": "s2"}).status_code == 200
    blocked = test_client.post("/chat", json={"question": "q", "session_id": "s2"})
    assert blocked.status_code == 429
    assert "run it locally" in blocked.json()["detail"].lower()


def test_empty_question_is_rejected(client):
    test_client, _ = client
    assert test_client.post("/chat", json={"question": "  ", "session_id": "s"}).status_code == 422


def test_health_reports_index_state(client):
    test_client, pipeline = client
    pipeline.retriever.collection.count.return_value = 5123
    body = test_client.get("/health").json()
    assert body["status"] == "ok" and body["chunks"] == 5123
