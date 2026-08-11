"""BE-06 tests: the background job contract.

- POST /jobs/triage answers 202 immediately with a Location header
- GET /jobs/triage/{id} reports progress and the final result
- the same idempotency_key never creates a second job
- unknown job ids are 404 with a clear error
"""

import time

import pytest
from fastapi.testclient import TestClient

from src.bg.store import JobStore
from src.llm.schema import TriageVerdict


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_STUB", "1")
    monkeypatch.setenv("LLM_ENABLED", "true")

    # Isolate the job store for the duration of the test (temp file, empty index).
    from app.main import app, bg_store

    bg_store.path = tmp_path / "jobs.jsonl"
    bg_store.jobs.clear()

    with TestClient(app) as test_client:
        yield test_client


def wait_for_job(client, job_id: str, timeout: float = 5.0) -> dict:
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


def test_post_answers_202_with_location_and_status_url(client):
    resp = client.post("/jobs/triage", json={"message": "i want to apply"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["status_url"] == f"/jobs/triage/{body['job_id']}"
    assert resp.headers["location"] == body["status_url"]


def test_job_reaches_succeeded_with_valid_result(client):
    resp = client.post("/jobs/triage", json={"message": "i want to apply"})
    job_id = resp.json()["job_id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "succeeded"
    assert job["attempts"] >= 1
    assert job["result"]["verdict"] in {v.value for v in TriageVerdict}
    assert job["error"] is None


def test_same_idempotency_key_returns_same_job(client):
    first = client.post(
        "/jobs/triage", json={"message": "i want to apply", "idempotency_key": "dup-check"}
    )
    second = client.post(
        "/jobs/triage", json={"message": "i want to apply", "idempotency_key": "dup-check"}
    )
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


def test_different_keys_create_different_jobs(client):
    a = client.post("/jobs/triage", json={"message": "i want to apply", "idempotency_key": "k-1"})
    b = client.post("/jobs/triage", json={"message": "i want to apply", "idempotency_key": "k-2"})
    assert a.json()["job_id"] != b.json()["job_id"]


def test_unknown_job_is_404(client):
    resp = client.get("/jobs/triage/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "job_not_found"