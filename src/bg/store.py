"""Durable job store: an append-only JSONL log plus an in-memory index.

Why JSONL and not just a dict? Two reasons, both assignment non-negotiables:

1. Crash recovery. If the API restarts with jobs half-done, the log is the
   source of truth: on startup the store re-reads every line and the index is
   rebuilt. Jobs left in "queued"/"running" are re-enqueued by the worker,
   which is the "jobs will run twice" case handled safely.
2. Auditability. Every state change is a line with a timestamp; you can always
   answer "what happened to this job".

Each job_id appears many times in the log (one line per state change). The
index keeps only the LATEST line per job_id. Writers serialize per job via the
worker lock, so a wrongly ordered append cannot corrupt the latest-state
resolution.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
JOB_LOG = DATA_DIR / "jobs.jsonl"

JOB_STATUSES = ("queued", "running", "succeeded", "failed")


class JobStore:
    def __init__(self, path: Path = JOB_LOG):
        self.path = path
        self._lock = threading.Lock()
        self.jobs: Dict[str, dict] = {}
        self._load()

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            record = json.loads(raw)
            # Latest line per job wins; older state lines are history only.
            self.jobs[record["job_id"]] = record

    def _append(self, record: dict) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
            self.jobs[record["job_id"]] = record

    # -- job lifecycle -----------------------------------------------------

    def create(
        self,
        job_id: str,
        message: str,
        idempotency_key: Optional[str] = None,
        kind: str = "triage",
        payload: Optional[dict] = None,
    ) -> dict:
        """Create a queued job. kind routes execution (worker dispatch):
        "triage" runs the LLM call, "report" renders a PDF (week 7)."""
        record = {
            "job_id": job_id,
            "idempotency_key": idempotency_key,
            "message": message,
            "kind": kind,
            "payload": payload,
            "status": "queued",
            "attempts": 0,
            "result": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._append(record)
        return record

    def get(self, job_id: str) -> Optional[dict]:
        return self.jobs.get(job_id)

    def find_by_idempotency_key(self, key: str, kind: Optional[str] = None) -> Optional[dict]:
        for job in self.jobs.values():
            if job.get("idempotency_key") == key and (
                kind is None or job.get("kind", "triage") == kind
            ):
                return job
        return None

    def touch(self, job_id: str, **changes) -> dict:
        """Apply pending state changes to the latest record and append a line."""
        current = self.jobs.get(job_id)
        if current is None:
            raise KeyError(job_id)
        record = dict(current)
        record.update(changes)
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._append(record)
        return record

    def interrupted_jobs(self) -> List[str]:
        """Jobs that must be re-enqueued after a restart (never finished)."""
        max_attempts = int(os.getenv("JOB_MAX_ATTEMPTS", "3"))
        return [
            job_id
            for job_id, job in self.jobs.items()
            if job["status"] in ("queued", "running") and job["attempts"] < max_attempts
        ]

    def __len__(self) -> int:
        return len(self.jobs)