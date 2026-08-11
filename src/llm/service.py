"""The triage job: prompt loading, stub mode, parse -> validate -> repair once,
quarantine, and a per-call cost log."""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from src.llm.clients import LLMClient
from src.llm.schema import TriageResult, TriageVerdict
from src.llm.settings import get_settings

# Repo root: src/llm -> src -> repo root, then prompts/ and logs/.
ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"


class LLMInvalidOutput(Exception):
    """The model's output could not be parsed even after one repair (maps to 422)."""


def load_prompt() -> str:
    """Load the versioned prompt file. The filename carries the version (…-v1.md)."""
    return (ROOT / "prompts" / "triage-v1.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Logging helpers (JSONL appends; safe to call concurrently)
# ---------------------------------------------------------------------------

def _log_jsonl(path: Path, record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")


def _quarantine(input_message: str, raw_output: str, error: Exception) -> None:
    _log_jsonl(
        LOG_DIR / "quarantine.jsonl",
        {
            "id": str(uuid.uuid4()),
            "at": datetime.now(timezone.utc).isoformat(),
            "input": input_message,
            "raw_output": raw_output,
            "error": str(error).replace("\n", " ")[:500],
        },
    )


def log_cost(model: str, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    _log_jsonl(
        LOG_DIR / "cost.jsonl",
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "cost_usd": round(cost_usd, 6),
        },
    )


# ---------------------------------------------------------------------------
# Stub mode (LLM_STUB=1): deterministic rule-based verdict, no network needed
# ---------------------------------------------------------------------------

APPLY_MARKERS = (
    "apply", "application", "interested", "hire me", "send my cv",
    "send my resume", "submit my", "want the job", "want this role",
    "want the role", "for this role",
)
QUESTION_MARKERS = (
    "question", "what ", "how ", "when ", "where ", "who ", "which ",
    "is it", "are you", "do you", "does the", "can i", "salary",
    "remote", "working hours", "why", "hiring",
)
SALES_MARKERS = (
    "sell", "selling", "service", "services", "pricing", "invoice",
    "package", "boost your", "grow your", "promotion", "sponsor",
)


def _stub_triage(message: str) -> TriageResult:
    lowered = message.lower()
    if any(marker in lowered for marker in SALES_MARKERS):
        return TriageResult(
            verdict=TriageVerdict.NOT_A_FIT,
            reasons=["Looks like a sales or promotional pitch.", "No interest in the job itself."],
        )
    if any(marker in lowered for marker in APPLY_MARKERS):
        return TriageResult(
            verdict=TriageVerdict.INTERESTED,
            reasons=["Wants to apply or is interested in the role.", "Mentions the job or application."],
        )
    if any(marker in lowered for marker in QUESTION_MARKERS):
        return TriageResult(
            verdict=TriageVerdict.QUESTION,
            reasons=["Asks a question about the role or process.", "Stops short of offering to apply."],
        )
    return TriageResult(
        verdict=TriageVerdict.OTHER,
        reasons=["Fits no other category.", "Not enough evidence in the message."],
    )


# ---------------------------------------------------------------------------
# Parse -> validate -> repair once
# ---------------------------------------------------------------------------

def _extract_json(text: str):
    """Pull a JSON object out of the model's reply (tolerates code fences)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def _parse_result(text: str) -> TriageResult:
    return TriageResult.model_validate(_extract_json(text))


def _usage_tokens(client: LLMClient, usage, fallback_pair) -> int:
    """Ollama's OpenAI-compatible endpoint may omit usage; fall back to estimation."""
    if usage is not None:
        return int(getattr(usage, "prompt_tokens", 0) or 0), int(
            getattr(usage, "completion_tokens", 0) or 0
        )
    return len(fallback_pair[0]) // 4, len(fallback_pair[1]) // 4


def triage_message(message: str, client: LLMClient = None) -> TriageResult:
    """Run the job: stub or real LLM, with parse/check/repair and logging."""
    client = client or LLMClient(cfg=get_settings())
    if client.cfg["stub"]:
        return _stub_triage(message)

    system_prompt = load_prompt()
    raw, usage = client.complete(system_prompt, message)
    try:
        result = _parse_result(raw)
        log_usage = _usage_tokens(client, usage, (system_prompt + message, raw))
        log_cost(client.cfg["model"], log_usage[0], log_usage[1],
                 (log_usage[0] + log_usage[1]) / 1000 * client.cfg["cost_per_1k"])
        return result
    except (ValueError, json.JSONDecodeError, ValidationError):
        pass  # fall through to one repair attempt

    repair_user = (
        "Your last answer was not valid JSON matching the required shape. "
        'Reply with ONLY a JSON object {"verdict": "...", "reasons": ["..."]} '
        "where verdict is exactly one of: interested, question, not_a_fit, other, "
        "and reasons is an array of one or two short strings. Nothing else.\n\n"
        f"Your bad answer was:\n{raw}"
    )
    raw2, usage2 = client.complete(system_prompt, repair_user)
    log_usage = _usage_tokens(client, usage2, (system_prompt + repair_user, raw2))
    log_cost(client.cfg["model"], log_usage[0], log_usage[1],
             (log_usage[0] + log_usage[1]) / 1000 * client.cfg["cost_per_1k"])

    try:
        return _parse_result(raw2)
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        _quarantine(message, raw2, exc)
        raise LLMInvalidOutput(
            "The LLM output could not be parsed even after one repair; "
            "the message was quarantined in logs/quarantine.jsonl."
        ) from exc