"""A17/A17-layer tests, updated for BE-06: the triage call now runs as a
background job, so these tests submit a job and poll the status endpoint.
All hermetic: LLM_STUB=1, no network.
"""

import time

import pytest
from fastapi.testclient import TestClient

from src.llm.schema import TriageVerdict


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")
    monkeypatch.setenv("LLM_ENABLED", "true")
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def wait_for_job(client, job_id: str, timeout: float = 5.0) -> dict:
    """Poll the status endpoint until the job is done (or the budget blows)."""
    deadline = time.time() + timeout
    while True:
        resp = client.get(f"/jobs/triage/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("succeeded", "failed"):
            return body
        if time.time() > deadline:
            raise AssertionError(
                f"job {job_id} did not finish in {timeout}s (last status: {body['status']})"
            )
        time.sleep(0.05)


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
    assert resp.status_code == 202
    job = wait_for_job(client, resp.json()["job_id"])
    assert job["status"] == "succeeded"
    assert job["result"]["verdict"] == expected


def test_stub_mode_output_matches_schema(client):
    resp = client.post("/jobs/triage", json={"message": "i want to apply"})
    job = wait_for_job(client, resp.json()["job_id"])
    result = job["result"]
    assert result["verdict"] in {v.value for v in TriageVerdict}
    assert 1 <= len(result["reasons"]) <= 2


def test_kill_switch_fails_job_and_alerts(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "0")
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "2")
    import json as _json
    from pathlib import Path

    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/jobs/triage", json={"message": "i want to apply"})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        job = wait_for_job(client, job_id, timeout=10.0)
        assert job["status"] == "failed"
        assert "disabled" in job["error"]

        # Someone must find out: a durable alert line must exist for this job.
        alert_path = Path(__file__).resolve().parents[1] / "logs" / "alerts.jsonl"
        assert alert_path.exists()
        last = _json.loads(alert_path.read_text(encoding="utf-8").splitlines()[-1])
        assert last["job_id"] == job_id


def test_stub_wins_over_kill_switch(monkeypatch):
    monkeypatch.setenv("LLM_STUB", "1")
    monkeypatch.setenv("LLM_ENABLED", "false")
    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/jobs/triage", json={"message": "i want to apply"})
        job = wait_for_job(client, resp.json()["job_id"])
        # The stub is the deterministic fallback: the job still succeeds.
        assert job["status"] == "succeeded"
        assert job["result"]["verdict"] == "interested"