"""Report settings (week 7), read from the environment like the other layers."""

import os
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[2]


def get_report_settings() -> Dict:
    return {
        # Where generated PDFs are written and served from (artifact storage).
        "reports_dir": Path(os.getenv("REPORTS_DIR", str(ROOT / "data" / "reports"))),
        # Daily auto-report fire time, UTC, "HH:MM" (scheduler stretch).
        "daily_time": os.getenv("REPORT_DAILY_TIME", "18:00"),
        # How often the scheduler loop wakes up to check the clock.
        "schedule_check_seconds": int(os.getenv("REPORT_SCHEDULE_CHECK_SECONDS", "30")),
    }