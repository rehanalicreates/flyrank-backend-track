"""OpenAI-compatible client with an explicit resilience policy.

Retry policy (per the assignment):
- retry ONLY on timeouts, 429 (rate limit) and 5xx (upstream errors)
- never retry 400 / 401 / 403
- backoff with jitter between attempts
- a single call may not take longer than LLM_TIMEOUT_SECONDS (default 60s)
"""

import time
import random

import httpx
from openai import OpenAI
from openai import APITimeoutError, APIStatusError

from src.llm.settings import get_settings


class LLMUnavailable(Exception):
    """Upstream refused or failed after retries (maps to 503)."""


class LLMTimeout(Exception):
    """The LLM did not answer within the budget even after retries (maps to 504)."""


class LLMDisabled(Exception):
    """Kill switch LLM_ENABLED=false (maps to 503 with a clear message)."""


def _backoff_with_jitter(attempt: int) -> float:
    """Exponential backoff plus a jitter term so simultaneous retries do not pile up."""
    return min(2 ** (attempt - 1), 8) + random.uniform(0, 1)


class LLMClient:
    def __init__(self, cfg=None):
        self.cfg = cfg or get_settings()

    def complete(self, system_prompt: str, user_message: str) -> str:
        """Single LLM call with the resilience policy. Returns assistant text."""
        if not self.cfg["enabled"]:
            raise LLMDisabled("LLM is disabled (LLM_ENABLED=false).")

        client = OpenAI(
            base_url=self.cfg["base_url"],
            api_key=self.cfg["api_key"],
            timeout=self.cfg["timeout"],
            max_retries=0,  # we run our own retry policy below
        )

        last_error = None
        for attempt in range(1, self.cfg["max_retries"] + 1):
            try:
                response = client.chat.completions.create(
                    model=self.cfg["model"],
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0,
                )
                return (
                    response.choices[0].message.content or "",
                    response.usage,
                )
            except APITimeoutError as exc:
                last_error = LLMTimeout("LLM timed out after retries.")
                if attempt < self.cfg["max_retries"]:
                    time.sleep(_backoff_with_jitter(attempt))
            except APIStatusError as exc:
                code = exc.status_code
                # 400/401/403 are permanent: never retry them.
                if code in (400, 401, 403):
                    raise LLMUnavailable(f"LLM refused the request with status {code}.")
                # 429 and 5xx are transient: retry with backoff.
                if code == 429 or code >= 500:
                    last_error = LLMUnavailable(
                        f"LLM upstream error {code} after retries."
                    )
                    if attempt < self.cfg["max_retries"]:
                        time.sleep(_backoff_with_jitter(attempt))
                    continue
                raise LLMUnavailable(f"LLM upstream error {code}.")
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_error = LLMUnavailable(
                    f"Could not reach the LLM at {self.cfg['base_url']}."
                )
                if attempt < self.cfg["max_retries"]:
                    time.sleep(_backoff_with_jitter(attempt))

        raise last_error