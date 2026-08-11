"""A17 eval runner.

Sends every labeled case in cases.json to the real /jobs/triage endpoint
(over HTTP through FastAPI's TestClient, so input validation and the full
request path are exercised, not just the LLM call), then scores the verdicts
against the labels.

Run from the repo root:
    python evals/run.py

Writes logs/eval-<timestamp>.jsonl with per-case gold vs predicted, and prints
the score line used in the README.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402 (imports after env decisions are fine, settings are read per request)

client = TestClient(app)


def main() -> None:
    results = []
    correct = 0

    for case in CASES:
        resp = client.post("/jobs/triage", json={"message": case["message"]})
        predicted = None
        if resp.status_code == 200:
            predicted = resp.json()["verdict"]
        ok = predicted == case["expected"]
        correct += 1 if ok else 0
        results.append(
            {
                "id": case["id"],
                "expected": case["expected"],
                "predicted": predicted,
                "http_status": resp.status_code,
                "ok": ok,
            }
        )
        flag = "PASS" if ok else "FAIL"
        print(f"[{flag}] {case['id']:<14} expected={case['expected']:<10} "
              f"predicted={predicted}")

    total = len(CASES)
    score = correct / total
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = ROOT / "logs" / f"eval-{run_id}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row) + "\n")

    print()
    print(f"Eval score: {correct}/{total} ({score * 100:.1f}%)")
    print(f"Detail log: {log_path.relative_to(ROOT)}")

    cost_path = ROOT / "logs" / "cost.jsonl"
    total_cost = 0.0
    total_tokens = 0
    if cost_path.exists():
        for line in cost_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                total_cost += float(row.get("cost_usd", 0))
                total_tokens += int(row.get("total_tokens", 0))
    print(f"Total LLM spend: ${total_cost:.6f} across {total_tokens} tokens "
          f"(local Ollama, price per 1k = {os.getenv('LLM_COST_PER_1K_TOKENS', '0')})")


if __name__ == "__main__":
    main()