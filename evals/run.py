"""A17/BE-06 eval runner.

Submits every labeled case in cases.json as a background job (the same way a
client would: POST -> 202 -> poll the status endpoint), then scores the
verdicts against the labels. Since BE-06 the LLM call happens on the worker,
so this exercise also proves the background pipeline end to end.

Run from the repo root:
    python evals/run.py

Writes logs/eval-<timestamp>.jsonl with per-case gold vs predicted, and prints
the score line used in the README.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402 (settings are read per request, so env order is fine)

PER_CASE_TIMEOUT = 90.0


def submit_and_wait(client, message: str):
    """POST (expect 202) then follow the status endpoint until done."""
    resp = client.post("/jobs/triage", json={"message": message})
    if resp.status_code != 202:
        return None, {"http_status": resp.status_code, "body": resp.json()}
    job_id = resp.json()["job_id"]
    deadline = time.time() + PER_CASE_TIMEOUT
    while True:
        body = client.get(f"/jobs/triage/{job_id}").json()
        if body["status"] == "succeeded":
            return body["result"]["verdict"], body
        if body["status"] == "failed":
            return None, body
        if time.time() > deadline:
            raise TimeoutError(f"job {job_id} still {body['status']} after {PER_CASE_TIMEOUT}s")
        time.sleep(0.25)


def main() -> None:
    with TestClient(app) as client:
        results = []
        correct = 0

        for case in CASES:
            predicted, body = submit_and_wait(client, case["message"])
            ok = predicted == case["expected"]
            correct += 1 if ok else 0
            results.append(
                {
                    "id": case["id"],
                    "expected": case["expected"],
                    "predicted": predicted,
                    "job_status": body.get("status"),
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