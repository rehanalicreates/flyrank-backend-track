"""Daily report scheduler (week 7 stretch: on a schedule).

A single asyncio task in the app lifespan wakes up every
REPORT_SCHEDULE_CHECK_SECONDS seconds and asks one question: has the daily
fire time (REPORT_DAILY_TIME, UTC) passed today, and has today already
fired? If both are true, it submits a report job through the exact same
pipeline as POST /reports (202-style store create, queue, worker, PDF), so
a scheduled run produces the same pollable job and the same artifact.

Two safety properties, both following the BE-06 philosophy:

1. "Jobs will run twice" is handled by persistence: every fire is appended
   to data/schedules.jsonl, so a restart mid-day cannot fire the report
   twice. The daily idempotency key is "daily-<date>".
2. If the server was down at 18:00, the next tick after startup fires the
   missed report once (catch-up), instead of silently skipping a day.
"""

import asyncio
import json
import threading
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Optional

from src.bg.store import JobStore
from src.bg.worker import JobWorker
from src.reports.settings import get_report_settings

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCHEDULE_LOG = DATA_DIR / "schedules.jsonl"


def parse_daily_time(value: str) -> time:
    """Parse "HH:MM" into a time. Bad values fall back to 18:00 UTC."""
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
        return time(hour=hour, minute=minute)
    except (ValueError, TypeError):
        return time(hour=18, minute=0)


def next_fire_at(day: date, daily_time: time) -> datetime:
    """The scheduled instant for one UTC day."""
    return datetime.combine(day, daily_time, tzinfo=timezone.utc)


def is_due(now: datetime, daily_time: time, last_fired_at: Optional[date]) -> bool:
    """True when now is past today's fire time and today has not fired yet."""
    if last_fired_at is not None and last_fired_at == now.date():
        return False
    return now >= next_fire_at(now.date(), daily_time)


class ReportScheduler:
    """Owns the schedule log and submits due daily report jobs."""

    def __init__(self, store: JobStore, worker: JobWorker, cfg=None, log_path: Path = SCHEDULE_LOG):
        self.store = store
        self.worker = worker
        self.cfg = cfg or get_report_settings()
        self.log_path = log_path
        self._lock = threading.Lock()
        self._last_fired: Optional[date] = self._load_last_fired()
        self.recent_fires: list[dict] = []

    # -- persistence -------------------------------------------------------

    def _load_last_fired(self) -> Optional[date]:
        latest: Optional[str] = None
        if self.log_path.exists():
            for raw in self.log_path.read_text(encoding="utf-8").splitlines():
                if raw.strip():
                    latest = json.loads(raw)["date"]
        return date.fromisoformat(latest) if latest else None

    def _record_fire(self, job_id: str) -> None:
        now = datetime.now(timezone.utc)
        line = {
            "date": now.date().isoformat(),
            "job_id": job_id,
            "fired_at": now.isoformat(),
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(line) + "\n")
            self._last_fired = now.date()
            self.recent_fires.append(line)

    # -- loop --------------------------------------------------------------

    async def run(self) -> None:
        """Wake up periodically and fire the daily report when due."""
        while True:
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - scheduling must never kill the app
                pass
            await asyncio.sleep(self.cfg["schedule_check_seconds"])

    def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        if not is_due(now, parse_daily_time(self.cfg["daily_time"]), self._last_fired):
            return
        job_id = f"report_{uuid.uuid4().hex[:12]}"
        self.store.create(
            job_id,
            None,
            idempotency_key=f"daily-{now.date().isoformat()}",
            kind="report",
            payload={"report_type": "tasks"},
        )
        self.worker.enqueue(job_id)
        self._record_fire(job_id)

    # -- introspection (GET /reports/schedule) -----------------------------

    def snapshot(self) -> dict:
        now = datetime.now(timezone.utc)
        daily_time = parse_daily_time(self.cfg["daily_time"])
        return {
            "daily_time": self.cfg["daily_time"],
            "schedule_check_seconds": self.cfg["schedule_check_seconds"],
            "last_fired_on": self._last_fired.isoformat() if self._last_fired else None,
            "next_run": next_fire_at(now.date(), daily_time).isoformat(),
            "recent_fires": self.recent_fires[-5:],
        }