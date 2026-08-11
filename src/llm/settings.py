"""Runtime settings read from the environment (and .env via python-dotenv).

Everything the LLM layer needs is configurable through environment variables
so the endpoint can be pointed at any OpenAI-compatible provider (Ollama,
OpenRouter, ...) without code changes.
"""

import os
from typing import Dict


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def get_settings() -> Dict:
    """Read settings fresh on every call (test-friendly, no import-time state)."""
    return {
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        "api_key": os.getenv("LLM_API_KEY", "ollama"),
        "model": os.getenv("LLM_MODEL", "qwen3:0.6b"),
        "stub": _env_bool("LLM_STUB", False),
        "enabled": _env_bool("LLM_ENABLED", True),
        "timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        "max_retries": int(os.getenv("LLM_MAX_RETRIES", "3")),
        "cost_per_1k": float(os.getenv("LLM_COST_PER_1K_TOKENS", "0")),
    }