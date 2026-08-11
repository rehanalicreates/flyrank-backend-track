# Task API with LLM triage

Week 2 (BE-01, CRUD Task API) plus A17 (`Put an LLM behind your API`) for the
**Backend AI Engineering** track at FlyRank.

Two things live in this repo:

1. A CRUD API that manages a to-do list: create, read, update, delete tasks.
2. An LLM-powered endpoint (`/jobs/triage`) that classifies a candidate
   message into one of four closed categories, with clean error handling,
   timeouts, retries, a stub mode, a kill switch, and a per-call cost log.

## Stack

- **FastAPI** - Python web framework, auto-generates OpenAPI docs
- **Pydantic v2** - request/response validation
- **openai + python-dotenv** - LLM client glue; works with Ollama locally or
  any OpenAI-compatible provider
- **pytest + httpx** - test suite (23 tests)

## Run it

```bash
pip install -r requirements.txt
copy .env.example .env   # Ollama defaults: qwen3:0.6b on localhost:11434
uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000  
Interactive docs (Swagger UI): http://127.0.0.1:8000/docs

## Endpoints

| Method | Path             | Status codes                                          |
|--------|------------------|-------------------------------------------------------|
| GET    | `/`              | 200 - API metadata                                    |
| GET    | `/health`        | 200 - liveness check                                  |
| POST   | `/tasks`         | 201 Created, 400 Bad Request                          |
| GET    | `/tasks`         | 200 OK                                                |
| GET    | `/tasks/{id}`    | 200 OK, 404 Not Found                                 |
| PUT    | `/tasks/{id}`    | 200 OK, 400 Bad Request, 404 Not Found                |
| DELETE | `/tasks/{id}`    | 204 No Content, 404 Not Found                         |
| POST   | `/jobs/triage`   | 200 OK, 400 Bad Request, 422 Unprocessable, 503/504 LLM errors |

## curl example: create a task

```
$ curl -i -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"title\":\"Buy milk\"}"
HTTP/1.1 201 Created

{"id":4,"title":"Buy milk","description":null,"completed":false,"created_at":"...","updated_at":"..."}
```

## curl example: triage a candidate message (runnable)

```
$ curl -X POST http://127.0.0.1:8000/jobs/triage \
    -H "Content-Type: application/json" \
    -d '{"message": "hi I am a product designer with 5 years of experience, I would like to apply for the open role"}'

{"verdict":"interested","reasons":["Wants to apply for the role","Mentions the open role"]}
```

Windows cmd note: single quotes do not work in cmd; use
`-d "{\"message\":\"...\"}"` there.

## Error examples

Missing/invalid input names the failing field with 400:

```
$ curl -i -X POST http://127.0.0.1:8000/jobs/triage -H "Content-Type: application/json" -d "{}"
HTTP/1.1 400 Bad Request

{"error":"validation_error","message":"'message' is required and must be a non-empty string."}
```

Other status codes:

- `422 invalid_llm_output` - the LLM reply failed validation even after one
  repair; the raw exchange is quarantined in `logs/quarantine.jsonl`
- `503 llm_disabled` - the kill switch `LLM_ENABLED=false` is on
- `503 llm_unavailable` - the LLM provider is down or refuses the request
- `504 llm_timeout` - the LLM did not answer within the budget (<=60s per call)

## The LLM layer (A17)

Job: **triage candidate messages** (see `JOB-CARD.md` and the versioned prompt
file `prompts/triage-v1.md`).

### Environment variables

| Variable                | Default                    | Meaning                                             |
|-------------------------|----------------------------|-----------------------------------------------------|
| `LLM_BASE_URL`          | `http://localhost:11434/v1`| OpenAI-compatible base URL (Ollama or OpenRouter)   |
| `LLM_API_KEY`           | `ollama`                   | API key for the provider                            |
| `LLM_MODEL`             | `qwen3:0.6b`               | Model name                                          |
| `LLM_STUB`              | `0`                        | `1` = rule-based verdicts, no network (dev/tests)   |
| `LLM_ENABLED`           | `true`                     | `false` = kill switch, endpoint answers 503         |
| `LLM_TIMEOUT_SECONDS`   | `60`                       | Max duration of a single LLM call                   |
| `LLM_MAX_RETRIES`       | `3`                        | Attempts per request                                |
| `LLM_COST_PER_1K_TOKENS`| `0`                        | Price per 1k tokens for the cost log (0 for Ollama) |

Provider swap = change the three `LLM_*` variables. OpenRouter example:
`LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_API_KEY=sk-or-...`,
`LLM_MODEL=openrouter/auto`.

### Behaviour contract

- Input: `POST /jobs/triage` with `{"message": "..."}` (required, non-empty).
- Output: `{"verdict": "interested|question|not_a_fit|other", "reasons": [...]}`
  - the verdict is a Pydantic enum; `reasons` has 1-2 items.
- The LLM reply is parsed, validated against the schema, and repaired exactly
  once. If it still fails, the request gets 422 and the exchange is appended
  to `logs/quarantine.jsonl`.
- Retry policy: retries happen only on timeout, `429`, and `5xx`, with
  exponential backoff plus jitter. `400/401/403` are never retried.
- Every LLM call is appended to `logs/cost.jsonl` (tokens + estimated USD).
- `LLM_STUB=1` returns deterministic keyword verdicts - no network needed.
- `LLM_ENABLED=false` makes the endpoint answer `503 llm_disabled`
  (or the stub fallback when `LLM_STUB=1`).

## Eval

`evals/cases.json` has 8 labeled cases (2 per category). The runner sends each
one through the real HTTP path and scores the verdicts:

```
$ python evals/run.py
[PASS] interested-1  expected=interested predicted=interested
... (8 cases) ...

Eval score: 8/8 (100.0%)
Total LLM spend: $0.000000 across 23235 tokens (local Ollama, price per 1k = 0)
```

Score computed on 11 Aug 2026 with `qwen3:0.6b` via local Ollama.
Per-case gold vs predicted detail: `logs/eval-<timestamp>.jsonl`.

## Swagger UI

![Swagger UI screenshot](screenshot.png)

Open http://127.0.0.1:8000/docs after starting the server to interact with the
API visually (both the task and the triage endpoints are there).

## Project structure

```
+-- app/
|   +-- main.py          # FastAPI app, routes, error handlers
|   +-- models.py        # Pydantic schemas (task request/response shapes)
|   +-- repository.py    # In-memory data layer
|   +-- exceptions.py    # Domain exceptions (framework-agnostic)
+-- src/llm/
|   +-- clients.py       # OpenAI-compatible client + retry/backoff/jitter policy
|   +-- service.py       # triage job: stub, parse/validate/repair, quarantine, cost log
|   +-- schema.py        # LLM output schema (verdict enum + reasons)
|   +-- settings.py      # runtime env settings
|   +-- hello.py         # connectivity check (prints "ready")
+-- prompts/
|   +-- triage-v1.md     # versioned prompt file for the job
+-- evals/
|   +-- cases.json       # 8 labeled eval cases
|   +-- run.py           # eval runner (scores over the real endpoint)
+-- tests/
|   +-- test_tasks.py    # CRUD + error paths
|   +-- test_llm.py      # validation, stub verdicts, schema shape, kill switch
+-- JOB-CARD.md
+-- .env.example
+-- requirements.txt
```

## Tests

```bash
pytest -v
```

23 tests: root endpoint, health check, full CRUD flow, missing/empty
title/message (400 naming the field), not-found errors (404), correct status
codes, stub-mode verdicts for all four categories, schema shape, and the kill
switch.