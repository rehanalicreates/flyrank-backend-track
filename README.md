# Task API with LLM triage and PDF reports

Week 2 (BE-01, CRUD Task API) plus A17 (`Put an LLM behind your API`),
BE-06 (`Your first background job`), and the week 7 PDF report generator
for the **Backend AI Engineering** track at FlyRank.

Four things live in this repo:

1. A CRUD API that manages a to-do list: create, read, update, delete tasks
   (SQLite-backed since week 7, so reports aggregate real SQL).
2. An LLM-powered triage job (`/jobs/triage`): classifies a candidate message
   into one of four closed categories, with clean error handling, timeouts,
   retries, a stub mode, a kill switch, and a per-call cost log (A17).
3. The same job executed as a **background job** (BE-06): `POST` answers 202
   instantly, a worker pool does the LLM call, `GET /jobs/triage/{id}` reports
   status and result. Idempotency, retries, and alerts are built in.
4. **PDF report generation** (week 7, `JOB-CARD-reports.md`): `POST /reports`
   answers 202, a worker runs SQL aggregation over the task database and
   renders a PDF artifact into `data/reports/`; the job result carries only a
   link (`GET /reports/{id}` -> `GET /reports/{id}/download` streams the
   file). A scheduler fires the report daily at `REPORT_DAILY_TIME` (stretch).

## Stack

- **FastAPI** - Python web framework, auto-generates OpenAPI docs
- **Pydantic v2** - request/response validation
- **openai + python-dotenv** - LLM client glue; works with Ollama locally or
  any OpenAI-compatible provider
- **sqlite3** (stdlib) - task storage and the report's SQL aggregation
- **reportlab** - PDF rendering (Platypus)
- **pytest + httpx** - test suite (42 tests)

## Run it

```bash
pip install -r requirements.txt
copy .env.example .env   # Ollama defaults: qwen3:0.6b on localhost:11434
uvicorn app.main:app --reload
```

API: http://127.0.0.1:8000  
Interactive docs (Swagger UI): http://127.0.0.1:8000/docs

## Endpoints

| Method | Path                   | Status codes                                          |
|--------|------------------------|-------------------------------------------------------|
| GET    | `/`                    | 200 - API metadata                                    |
| GET    | `/health`              | 200 - liveness check                                  |
| POST   | `/tasks`               | 201 Created, 400 Bad Request                          |
| GET    | `/tasks`               | 200 OK                                                |
| GET    | `/tasks/{id}`          | 200 OK, 404 Not Found                                 |
| PUT    | `/tasks/{id}`          | 200 OK, 400 Bad Request, 404 Not Found                |
| DELETE | `/tasks/{id}`          | 204 No Content, 404 Not Found                         |
| POST   | `/jobs/triage`         | 202 Accepted, 400 Bad Request (LLM runs in background)|
| GET    | `/jobs/triage/{id}`    | 200 OK, 404 Not Found                                 |
| POST   | `/reports`             | 202 Accepted (PDF renders in background)              |
| GET    | `/reports/{id}`        | 200 OK, 404 Not Found (status + artifact link)        |
| GET    | `/reports/{id}/download`| 200 OK PDF, 404, 409 if not succeeded yet            |
| GET    | `/reports/schedule`    | 200 OK (daily scheduler state)                        |

## curl example: create a task

```
$ curl -i -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"title\":\"Buy milk\"}"
HTTP/1.1 201 Created

{"id":4,"title":"Buy milk","description":null,"completed":false,"created_at":"...","updated_at":"..."}
```

## curl example: triage a candidate message (runnable, BE-06 background flow)

The endpoint answers instantly; the LLM call happens on a worker. Poll the
status endpoint until the result is there:

```
$ curl -i -X POST http://127.0.0.1:8000/jobs/triage \
    -H "Content-Type: application/json" \
    -d '{"message": "hi I am a product designer with 5 years of experience, I would like to apply for the open role"}'

HTTP/1.1 202 Accepted
location: /jobs/triage/triage_29de8a4db36b

{"job_id":"triage_29de8a4db36b","status":"queued","status_url":"/jobs/triage/triage_29de8a4db36b"}
```

```
$ curl http://127.0.0.1:8000/jobs/triage/triage_29de8a4db36b

{"job_id":"triage_29de8a4db36b","idempotency_key":null,"status":"succeeded",
 "attempts":1,"result":{"verdict":"interested","reasons":["Wants to apply for the role","Mentions the open role"]},
 "error":null,"created_at":"...","updated_at":"..."}
```

Statuses: `queued` -> `running` -> `succeeded` (result present) or `failed`
(error present).

Windows cmd note: single quotes do not work in cmd; use
`-d "{\"message\":\"...\"}"` there.

## The PDF report (week 7)

`JOB-CARD-reports.md` is the one-page job brief. The pipeline:

1. **Query** - the worker runs SQL aggregation over `data/tasks.db`
   (`src/reports/queries.py`): totals, status breakdown, tasks created per
   day (last 14), tasks by hour, recent tasks.
2. **Render** - `src/reports/render.py` turns the stats into a PDF with
   ReportLab (summary grid, tables, footer with job id and timestamp).
3. **Artifact** - the PDF is written to `data/reports/{job_id}.pdf` once and
   the job result carries only metadata: `file_name`, `size_bytes`,
   `download_url`. No bytes travel in JSON (store and link, not 20 MB).

```
$ curl -i -X POST http://127.0.0.1:8000/reports -H "Content-Type: application/json" \
    -d '{"report_type": "tasks"}'
HTTP/1.1 202 Accepted
location: /reports/report_fe1d908ccb71
{"job_id":"report_fe1d908ccb71","status":"queued","status_url":"/reports/report_fe1d908ccb71"}
```

```
$ curl http://127.0.0.1:8000/reports/report_fe1d908ccb71
{"job_id":"report_fe1d908ccb71","status":"succeeded","attempts":1,
 "artifact":{"file_name":"report_fe1d908ccb71.pdf","size_bytes":4513,
             "download_url":"/reports/report_fe1d908ccb71/download","report_type":"tasks"},
 "summary":{"total_tasks":14,"completed":10,"open":4,"completion_rate":71.4,...}}
```

```
$ curl -o sample-report.pdf http://127.0.0.1:8000/reports/report_fe1d908ccb71/download
HTTP/1.1 200 OK   (content-type: application/pdf, content-length: 4513)
```

Same contract as triage: idempotency key dedupe, `queued`/`running`/
`succeeded`/`failed`, retries with backoff, alerts on final failure. The
download endpoint answers 409 `report_not_ready` until the job succeeds and
validates the job id before touching the filesystem. The scheduler (stretch)
fires the daily report at `REPORT_DAILY_TIME` (UTC) through the same
pipeline, persisted in `data/schedules.jsonl` so a restart never fires
twice: `GET /reports/schedule` shows its state.

## Idempotency (BE-06: "jobs will run twice")

Two layers:

1. **Client side** - resend the same `idempotency_key` and you get the SAME
   job back, never a duplicate:

```
$ curl -i -X POST http://127.0.0.1:8000/jobs/triage -H "Content-Type: application/json" \
    -d '{"message":"I want to apply","idempotency_key":"contact-form-42"}'
HTTP/1.1 202 Accepted   (same job_id on every retry)
```

2. **Worker side** - the job is a pure function of its input message, so if a
   restart replays an unfinished job (status left in queued/running), a re-run
   produces the same verdict. Jobs in "succeeded"/"failed" are never executed
   again, and duplicate queue tokens collapse onto one execution (in-flight
   guard). The result is that running twice is safe and costs nothing extra.

## Error examples

Missing/invalid input names the failing field with 400:

```
$ curl -i -X POST http://127.0.0.1:8000/jobs/triage -H "Content-Type: application/json" -d "{}"
HTTP/1.1 400 Bad Request

{"error":"validation_error","message":"'message' is required and must be a non-empty string."}
```

Unknown job ids are 404:

```
$ curl -i http://127.0.0.1:8000/jobs/triage/does-not-exist
HTTP/1.1 404 Not Found

{"detail":{"error":"job_not_found","message":"No job with id does-not-exist."}}
```

Status codes for the job pipeline:

- `202` - accepted; the LLM call runs in the background
- `400` - validation error with the field named
- `404` - unknown job id
- `503` - the worker pool is unavailable (no lifespan / kill switch case
  surfaces here as job `failed`)
- `504` - not used at the HTTP layer anymore: a slow LLM fails the JOB, and
  the job-level retries handle it (see below)

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
| `LLM_ENABLED`           | `true`                     | `false` = kill switch, jobs fail with llm_disabled  |
| `LLM_TIMEOUT_SECONDS`   | `60`                       | Max duration of a single LLM call                   |
| `LLM_MAX_RETRIES`       | `3`                        | Attempts per request                                |
| `LLM_COST_PER_1K_TOKENS`| `0`                        | Price per 1k tokens for the cost log (0 for Ollama) |
| `WORKER_COUNT`          | `2`                        | Worker tasks in the pool                            |
| `JOB_MAX_ATTEMPTS`      | `3`                        | Execution attempts before a job is failed           |
| `ALERT_WEBHOOK_URL`     | (empty)                    | Optional webhook for job-failed alerts              |
| `REPORTS_DIR`           | `data/reports`             | Where generated PDFs live (artifacts)               |
| `REPORT_DAILY_TIME`     | `18:00`                    | Daily auto-report fire time, UTC (scheduler)        |
| `REPORT_SCHEDULE_CHECK_SECONDS` | `30`              | Scheduler wake-up interval                           |

Provider swap = change the three `LLM_*` variables. OpenRouter example:
`LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_API_KEY=sk-or-...`,
`LLM_MODEL=openrouter/auto`.

### The background job (BE-06) contract

- `POST /jobs/triage` with `{"message": "..."}` (required, non-empty; optional
  `idempotency_key`) answers **202** with `job_id` + `status_url` and a
  `Location` header. No LLM call happens on the request: the worker pool
  (started in the app lifespan) picks the job from its queue and runs the
  triage call off-thread.
- `GET /jobs/triage/{job_id}` reports `queued` / `running` / `succeeded` /
  `failed`, plus `attempts`, `result`, and `error`.
- Job store: append-only `data/jobs.jsonl` (latest line per job wins). After a
  restart, unfinished jobs are re-enqueued - running twice is safe and
  idempotent (see "Idempotency").
- Retries: a failing job is retried up to `JOB_MAX_ATTEMPTS` with exponential
  backoff + jitter, then marked `failed`.
- Alerts: every final failure appends a line to `logs/alerts.jsonl` (who/how/
  when) and, if `ALERT_WEBHOOK_URL` is set, POSTs it there best-effort.
- Stub and kill switch behaviour moved into the job: with `LLM_STUB=1` jobs
  succeed with deterministic verdicts; with `LLM_ENABLED=false` jobs fail
  (error `llm_disabled`), which exercises the retry + alert path.

## Eval

`evals/cases.json` has 8 labeled cases (2 per category). The runner submits
each one as a background job over the real HTTP path (POST -> 202 -> poll the
status endpoint) and scores the verdicts:

```
$ python evals/run.py
[PASS] interested-1  expected=interested predicted=interested
... (8 cases) ...

Eval score: 8/8 (100.0%)
Total LLM spend: $0.000000 across 33112 tokens (local Ollama, price per 1k = 0)
```

Score computed on 11 Aug 2026 with `qwen3:0.6b` via local Ollama, through the
BE-06 background pipeline.
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
|   +-- repository.py    # SQLite task store (same CRUD interface as before)
|   +-- exceptions.py    # Domain exceptions (framework-agnostic)
+-- src/llm/
|   +-- clients.py       # OpenAI-compatible client + retry/backoff/jitter policy
|   +-- service.py       # triage job: stub, parse/validate/repair, quarantine, cost log
|   +-- schema.py        # LLM output schema (verdict enum + reasons + idempotency_key)
|   +-- settings.py      # runtime env settings
|   +-- hello.py         # connectivity check (prints "ready")
+-- src/bg/
|   +-- store.py         # durable JSONL job store, replayable after restart
|   +-- worker.py        # queue consumer pool: retries, backoff, in-flight guard
|   +-- alerts.py        # job-failed alerts (JSONL + optional webhook)
|   +-- schema.py        # job report / accepted response schemas
|   +-- settings.py      # WORKER_COUNT, JOB_MAX_ATTEMPTS, ALERT_WEBHOOK_URL
+-- src/reports/
|   +-- queries.py       # SQL aggregation over data/tasks.db (read-only)
|   +-- render.py        # ReportLab PDF rendering (Platypus tables)
|   +-- job.py           # the report job: query + render + artifact metadata
|   +-- artifacts.py     # safe artifact path resolution (job id validation)
|   +-- scheduler.py     # daily fire loop (stretch), schedules.jsonl
|   +-- schema.py        # report request / accepted / response schemas
|   +-- settings.py      # REPORTS_DIR, REPORT_DAILY_TIME, check seconds
+-- prompts/
|   +-- triage-v1.md     # versioned prompt file for the job
+-- evals/
|   +-- cases.json       # 8 labeled eval cases
|   +-- run.py           # eval runner (submits jobs, polls, scores)
+-- tests/
|   +-- test_tasks.py    # CRUD + error paths
|   +-- test_llm.py      # validation, stub verdicts, schema shape, kill switch + alerts
|   +-- test_bg.py       # 202/Location, status flow, idempotency, 404
|   +-- test_reports.py  # report flow, artifact link, PDF download, aggregation math, scheduler
+-- JOB-CARD.md
+-- JOB-CARD-reports.md
+-- .env.example
+-- requirements.txt
```

Runtime data is git-ignored: `logs/` (cost, quarantine, alerts, eval details)
and `data/` (the job log).

## Tests

```bash
pytest -v
```

42 tests: root endpoint, health check, full CRUD flow, missing/empty
title/message (400 naming the field), not-found errors (404), correct status
codes, stub-mode verdicts for all four categories, schema shape, the kill
switch with alert verification, the background contract (202 + Location,
queued -> running -> succeeded, idempotency keys, unknown job 404), and the
report generator (202 + Location, artifact metadata instead of bytes, PDF
download, 409 before success, unknown/foreign job 404, idempotency,
schedule endpoint, exact SQL aggregation math, PDF render on empty and
populated data, scheduler due math and no double fire).