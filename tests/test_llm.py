"""A17 tests: input validation (400 naming the field), stub-mode verdicts,
schema shape, and the kill switch. All hermetic: LLM_STUB=1, no network.

The app reads settings from the environment on every request, so monkeypatch
is safe even though app.main is imported at module level.
"""

import pytest
from fastapi.testclient import TestClient

from src.llm.schema import TriageVerdict


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")
    monkeypatch.setenv("LLM_ENABLED", "true")
    from app.main import app

    return TestClient(app)


def test_missing_message_returns_400_naming_the_field(client):
    resp = client.post("/jobs/triage", json={})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "validation_error"
    assert "message" in body["message"]


def test_wrong_field_returns_400_naming_the_field(client):
    resp = client.post("/jobs/triage", json={"text": "hi"})
    assert resp.status_code == 400
    assert "message" in resp.json()["message"]


def test_empty_message_returns_400(client):
    resp = client.post("/jobs/triage", json={"message": ""})
    assert resp.status_code == 400
    assert "message" in resp.json()["message"]


@pytest.mark.parametrize(
    "message,expected",
    [
        ("I want to apply for the job. How do I send my CV?", "interested"),
        ("Is the role remote? Are you hiring in Europe?", "question"),
        ("We sell SEO backlinks, DM for pricing.", "not_a_fit"),
        ("The printer on floor 2 is out of paper.", "other"),
    ],
)
def test_stub_mode_returns_expected_verdicts(client, message, expected):
    resp = client.post("/jobs/triage", json={"message": message})
    assert resp.status_code == 200
    assert resp.json()["verdict"] == expected


def test_stub_mode_output_matches_schema(client):
    resp = client.post("/jobs/triage", json={"message": "i want to apply"})
    body = resp.json()
    assert body["verdict"] in {v.value for v in TriageVerdict}
    assert 1 <= len(body["reasons"]) <= 2


def test_kill_switch_returns_503_without_stub(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "0")
    monkeypatch.setenv("LLM_ENABLED", "false")
    from app.main import app

    resp = TestClient(app).post(
        "/jobs/triage", json={"message": "i want to apply"}
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_disabled"


def test_stub_wins_over_kill_switch(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")
    monkeypatch.setenv("LLM_ENABLED", "false")
    from app.main import app

    resp = TestClient(app).post(
        "/jobs/triage", json={"message": "i want to apply"}
    )
    # Stub is the deterministic fallback: it still answers.
    assert resp.status_code == 200
    assert resp.json()["verdict"] == "interested"