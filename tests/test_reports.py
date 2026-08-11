"""Week 7 tests: the PDF report generator.

Covers:
- POST /reports answers 202 with a Location header (same contract as triage)
- the job reaches succeeded with artifact metadata (never PDF bytes)
- GET /reports/{id}/download streams a valid PDF from disk
- download before success is 409, unknown ids are 404
- idempotency: the same key returns the same job
- SQL aggregation math over a controlled database (unit)
- PDF rendering produces a real PDF file (unit)
- scheduler due/fire-time math, including no double fire (unit)
"""

import sqlite3
import time as time_mod
from datetime import date, datetime, time, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    # Never fire the daily report during tests.
    monkeypatch.setenv("REPORT_DAILY_TIME", "23:59")

    from app.main import app, bg_store

    bg_store.path = tmp_path / "jobs.jsonl"
    bg_store.jobs.clear()

    with TestClient(app) as test_client:
        yield test_client


def wait_for_job(client, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time_mod.time() + timeout
    while True:
        resp = client.get(f"/reports/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in ("succeeded", "failed"):
            return body
        if time_mod.time() > deadline:
            raise AssertionError(
                f"report job {job_id} did not finish in {timeout}s "
                f"(last status: {body['status']})"
            )
        time_mod.sleep(0.05)


# ---------------------------------------------------------------- API flow

def test_post_report_answers_202_with_location(client):
    resp = client.post("/reports", json={"report_type": "tasks"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_id"].startswith("report_")
    assert body["status_url"] == f"/reports/{body['job_id']}"
    assert resp.headers["location"] == body["status_url"]


def test_report_job_succeeds_with_artifact_not_bytes(client):
    client.post("/tasks", json={"title": "Report A"})
    client.post("/tasks", json={"title": "Report B", "completed": True})
    job_id = client.post("/reports", json={}).json()["job_id"]

    job = wait_for_job(client, job_id)
    assert job["status"] == "succeeded"
    assert job["attempts"] >= 1
    assert job["error"] is None
    assert job["report_type"] == "tasks"

    artifact = job["artifact"]
    assert artifact["file_name"].endswith(".pdf")
    assert artifact["size_bytes"] > 0
    assert artifact["download_url"] == f"/reports/{job_id}/download"

    summary = job["summary"]
    assert summary["total_tasks"] >= 2
    assert summary["completed"] >= 1
    assert summary["completion_rate"] is not None


def test_download_returns_pdf_bytes(client):
    job_id = client.post("/reports", json={}).json()["job_id"]
    wait_for_job(client, job_id)

    resp = client.get(f"/reports/{job_id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_download_does_not_exist_before_success(client):
    from app.main import bg_store

    job_id = "report_" + "0" * 12
    bg_store.create(
        job_id, None, None, kind="report", payload={"report_type": "tasks"}
    )
    bg_store.touch(job_id, status="failed", error="boom")
    # The failed job is never enqueued, so no worker runs it: deterministic.
    resp = client.get(f"/reports/{job_id}/download")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "report_not_ready"


def test_same_idempotency_key_returns_same_job(client):
    first = client.post("/reports", json={"idempotency_key": "daily-2026-08-11"})
    second = client.post("/reports", json={"idempotency_key": "daily-2026-08-11"})
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


def test_unknown_report_is_404(client):
    assert client.get("/reports/nope").status_code == 404
    assert client.get("/reports/nope/download").status_code == 404


def test_triage_job_is_not_a_report(client):
    job_id = client.post("/jobs/triage", json={"message": "hi"}).json()["job_id"]
    assert client.get(f"/reports/{job_id}").status_code == 404
    assert client.get(f"/reports/{job_id}/download").status_code == 404


def test_schedule_endpoint_reports_state(client):
    resp = client.get("/reports/schedule")
    assert resp.status_code == 200
    body = resp.json()
    assert body["daily_time"] == "23:59"
    assert "next_run" in body
    assert "recent_fires" in body


# --------------------------------------------------------- SQL aggregation

def _make_db(path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT NOT NULL, description TEXT, completed INTEGER NOT NULL"
        " DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    for title, completed, created_at in rows:
        conn.execute(
            "INSERT INTO tasks (title, description, completed, created_at, updated_at)"
            " VALUES (?, NULL, ?, ?, ?)",
            (title, int(completed), created_at, created_at),
        )
    conn.commit()
    conn.close()


def test_aggregate_tasks_math(monkeypatch, tmp_path):
    from src.reports.queries import aggregate_tasks

    db = tmp_path / "agg.db"
    today = datetime.now(timezone.utc).date().isoformat()
    _make_db(
        db,
        [
            ("One", False, f"{today}T09:00:00+00:00"),
            ("Two", True, f"{today}T09:30:00+00:00"),
            ("Three", False, f"{today}T15:00:00+00:00"),
        ],
    )

    stats = aggregate_tasks(db)
    assert stats["totals"] == {"total": 3, "completed": 1, "open": 2}
    assert stats["completion_rate"] == pytest.approx(33.3, abs=0.1)
    assert stats["by_status"] == [
        {"state": "Done", "count": 1},
        {"state": "Open", "count": 2},
    ]
    assert stats["per_day"] == [{"day": today, "count": 3}]
    hours = {row["hour"]: row["count"] for row in stats["by_hour"]}
    assert hours == {"09": 2, "15": 1}
    assert stats["summary"]["total_tasks"] == 3
    assert stats["summary"]["recents_count"] == 3


def test_aggregate_tasks_empty_db(monkeypatch, tmp_path):
    from src.reports.queries import aggregate_tasks

    db = tmp_path / "empty.db"
    _make_db(db, [])
    stats = aggregate_tasks(db)
    assert stats["totals"] == {"total": 0, "completed": 0, "open": 0}
    assert stats["completion_rate"] is None
    assert stats["by_status"] == []
    assert stats["summary"]["total_tasks"] == 0


# ------------------------------------------------------------------ render

def test_render_produces_pdf(tmp_path):
    import sqlite3

    from src.reports.queries import aggregate_tasks
    from src.reports.render import render_tasks_pdf

    db = tmp_path / "render.db"
    today = datetime.now(timezone.utc).date().isoformat()
    _make_db(
        db,
        [
            ("Render me", False, f"{today}T10:00:00+00:00"),
            ("Also me", True, f"{today}T11:00:00+00:00"),
        ],
    )
    stats = aggregate_tasks(db)
    out = tmp_path / "out.pdf"
    render_tasks_pdf(stats, out, job_id="report_test")
    assert out.exists()
    assert out.stat().st_size > 1000
    assert out.read_bytes().startswith(b"%PDF")


def test_render_empty_db_still_builds(tmp_path):
    import sqlite3

    from src.reports.queries import aggregate_tasks
    from src.reports.render import render_tasks_pdf

    db = tmp_path / "empty_render.db"
    _make_db(db, [])
    out = tmp_path / "empty.pdf"
    render_tasks_pdf(aggregate_tasks(db), out, job_id="report_empty")
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")


# ---------------------------------------------------------------- scheduler

def test_scheduler_time_math():
    from src.reports.scheduler import is_due, next_fire_at, parse_daily_time

    daily = time(hour=18, minute=0)
    at_1830 = datetime(2026, 8, 11, 18, 30, tzinfo=timezone.utc)
    at_1000 = datetime(2026, 8, 11, 10, 0, tzinfo=timezone.utc)

    assert is_due(at_1830, daily, None) is True
    assert is_due(at_1830, daily, date(2026, 8, 11)) is False
    assert is_due(at_1000, daily, None) is False
    assert next_fire_at(date(2026, 8, 11), daily) == datetime(
        2026, 8, 11, 18, 0, tzinfo=timezone.utc
    )
    assert parse_daily_time("23:59") == time(hour=23, minute=59)
    assert parse_daily_time("garbage") == time(hour=18, minute=0)


def test_scheduler_tick_fires_once(tmp_path):
    from src.bg.store import JobStore
    from src.reports.scheduler import ReportScheduler

    store = JobStore(path=tmp_path / "jobs.jsonl")
    fired = []

    class FakeWorker:
        def enqueue(self, job_id: str) -> None:
            fired.append(job_id)

    cfg = {
        "reports_dir": tmp_path / "reports",
        "daily_time": "00:00",  # always already past, today
        "schedule_check_seconds": 30,
    }
    scheduler = ReportScheduler(
        store, FakeWorker(), cfg=cfg, log_path=tmp_path / "schedules.jsonl"
    )

    scheduler._tick()
    assert len(fired) == 1
    job = store.get(fired[0])
    assert job["kind"] == "report"
    assert job["payload"] == {"report_type": "tasks"}
    assert job["idempotency_key"] == f"daily-{datetime.now(timezone.utc).date().isoformat()}"

    scheduler._tick()
    scheduler._tick()
    assert len(fired) == 1, "the daily report must never fire twice per day"