"""Alert sink for background jobs (BE-06 non-negotiable: someone must find out).

Every final job failure is appended to logs/alerts.jsonl (the audit trail) and,
if ALERT_WEBHOOK_URL is set, pushed there best-effort (never crashes the
worker, timeout 5s, silent on failure - the JSONL line is the source of truth).
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.bg.settings import get_bg_settings

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"


async def _push_webhook(record: dict, url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json=record)
    except Exception:
        pass  # the JSONL line below is the durable record


async def alert_job_failed(job_id: str, error: str, attempts: int) -> None:
    record = {
        "id": str(uuid.uuid4()),
        "at": datetime.now(timezone.utc).isoformat(),
        "kind": "job_failed",
        "job_id": job_id,
        "error": error[:500],
        "attempts": attempts,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "alerts.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    webhook = get_bg_settings()["alert_webhook_url"]
    if webhook:
        await _push_webhook(record, webhook)