"""Connectivity check (A17 stage 0 checkpoint).

Runs one chat completion against the configured LLM and prints "ready" when
the endpoint answers. Same client/resilience code as the API itself.

Run from the repo root:
    python -m src.llm.hello
"""

from src.llm.clients import LLMClient
from src.llm.settings import get_settings

CHECK_PROMPT = "You are a connectivity check. Reply with exactly one word: ready"


def main() -> int:
    client = LLMClient(cfg=get_settings())
    reply, _usage = client.complete(CHECK_PROMPT, "ping")
    text = reply.strip().lower()
    print(f"MODEL  : {client.cfg['model']}")
    print(f"REPLY  : {reply.strip()[:120]!r}")
    if "ready" in text:
        print("ready")
        return 0
    print("not-ready")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())