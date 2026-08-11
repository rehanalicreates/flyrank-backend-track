"""Background job settings (BE-06), read from the environment like the LLM layer."""

import os
from typing import Dict


def get_bg_settings() -> Dict:
    return {
        "worker_count": int(os.getenv("WORKER_COUNT", "2")),
        "max_attempts": int(os.getenv("JOB_MAX_ATTEMPTS", "3")),
        "alert_webhook_url": os.getenv("ALERT_WEBHOOK_URL", "").strip(),
    }