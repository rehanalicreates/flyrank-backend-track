"""SQL aggregation over the task database (week 7).

The report job runs these queries against data/tasks.db (the same SQLite file
the CRUD API writes) and feeds the numbers into the PDF renderer. This is the
"query your data" half of the assignment: real SQL (COUNT, GROUP BY, AVG,
substr/day bucketing) over real rows, not a copy maintained for reporting.

Times are stored as UTC ISO strings, so day/hour bucketing is done on the
raw string with substr (deterministic, no SQLite date-parsing edge cases).
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from app.repository import DB_PATH

_MAX_DAYS = 14
_MAX_RECENTS = 10


def _connect(db_path: Path) -> sqlite3.Connection:
    """Read-only connection: a report must never mutate the API's data."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def aggregate_tasks(db_path: Path = DB_PATH) -> Dict:
    """Run the report queries; return plain dicts the renderer can consume."""
    conn = _connect(db_path)
    try:
        totals_row = conn.execute(
            "SELECT COUNT(*) AS total,"
            " COALESCE(SUM(completed), 0) AS completed"
            " FROM tasks"
        ).fetchone()
        total = int(totals_row["total"])
        completed = int(totals_row["completed"])
        open_count = total - completed

        by_status = [
            {"state": "Done" if bool(r["completed"]) else "Open", "count": int(r["n"])}
            for r in conn.execute(
                "SELECT completed, COUNT(*) AS n FROM tasks GROUP BY completed"
            )
        ]
        by_status = sorted(by_status, key=lambda r: r["state"])

        per_day = [
            {"day": r["day"], "count": int(r["n"])}
            for r in conn.execute(
                "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS n"
                " FROM tasks"
                f" WHERE substr(created_at, 1, 10) >= date('now', '-{_MAX_DAYS - 1} day')"
                " GROUP BY day ORDER BY day ASC"
            )
        ]

        by_hour = [
            {"hour": r["hour"], "count": int(r["n"])}
            for r in conn.execute(
                "SELECT substr(created_at, 12, 2) AS hour, COUNT(*) AS n"
                " FROM tasks GROUP BY hour ORDER BY hour ASC"
            )
        ]

        recents = [
            {
                "id": int(r["id"]),
                "title": r["title"],
                "state": "Done" if bool(r["completed"]) else "Open",
                "created_at": (r["created_at"] or "")[:16],
            }
            for r in conn.execute(
                "SELECT id, title, completed, created_at FROM tasks"
                " ORDER BY id DESC LIMIT ?",
                (_MAX_RECENTS,),
            )
        ]
        recents = list(reversed(recents))

        title_stats = conn.execute(
            "SELECT AVG(length(title)) AS avg_len, MAX(length(title)) AS max_len FROM tasks"
        ).fetchone()
    finally:
        conn.close()

    completion_rate = (completed / total * 100) if total else None

    return {
        "totals": {"total": total, "completed": completed, "open": open_count},
        "completion_rate": completion_rate,
        "by_status": by_status,
        "per_day": per_day,
        "by_hour": by_hour,
        "recents": recents,
        "title_stats": {
            "avg_len": round(float(title_stats["avg_len"]), 1) if total else None,
            "max_len": int(title_stats["max_len"]) if total else None,
        },
        # The snapshot carried back in the job result (small, JSON-safe).
        "summary": {
            "total_tasks": total,
            "completed": completed,
            "open": open_count,
            "completion_rate": (
                round(completion_rate, 1) if completion_rate is not None else None
            ),
            "recents_count": len(recents),
        },
    }