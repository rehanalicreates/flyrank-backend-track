# JOB-CARD - Generate a PDF task report

## The job (one sentence)

Given no input (or a report type), aggregate the task database with SQL and
render the numbers into a PDF file, stored on disk and returned to the
client as a link: `POST /reports` answers 202, a worker renders the artifact,
`GET /reports/{job_id}` reports status and the artifact link, and
`GET /reports/{job_id}/download` streams the PDF.

## Why this job

"Generate a report" is the most classic background job in software; every
SaaS ships it. It deliberately combines everything from the last four weeks
into one feature: SQL aggregation over the data the API already manages
(week 1 CRUD, now SQLite-backed), artifact handling (store and link, never
pass megabytes through JSON), and the BE-06 job pattern (202, poll, retries,
alerts, idempotency).

## Input

- Optional JSON body: `{"report_type": "tasks"}` (only "tasks" for now;
  the shape is kept so future report types add a branch in the job, not a
  new pipeline). Optional `idempotency_key` to dedupe client retries.

## Output

- Job result: artifact metadata only (`file_name`, `size_bytes`,
  `download_url`, `report_type`) plus a small `summary` snapshot. The PDF
  bytes live at `data/reports/{job_id}.pdf`.
- The PDF itself: summary grid, tasks by status, tasks created per day
  (last 14 days), tasks by hour of day (UTC), ten most recent tasks.

## Rules

1. The job may never ship PDF bytes inside the job JSON: result = link.
2. The download endpoint validates the job id before touching the path
   (`report_[0-9a-f]{12}` only), so a request cannot escape the reports dir.
3. A report is a pure function of the database: re-running after a restart
   produces the same artifact, so replay is safe (BE-06 "jobs will run twice"
   property).
4. Aggregation runs read-only against the same `data/tasks.db` the CRUD API
   writes; a report never mutates business data.
5. If the database is empty the PDF still renders, with an explicit
   "no tasks" note instead of blank tables.

## Schedule (stretch)

A lifespan task checks every `REPORT_SCHEDULE_CHECK_SECONDS` (default 30) and
fires the daily report at `REPORT_DAILY_TIME` (default 18:00, UTC) as an
ordinary report job with idempotency key `daily-<date>`. Fires are persisted
to `data/schedules.jsonl`: a restart mid-day cannot fire twice, and a missed
day catches up on the next tick. Scheduler state: `GET /reports/schedule`.

## Failure behaviour

Same as every job in the store: retried up to `JOB_MAX_ATTEMPTS` with
exponential backoff plus jitter, then marked `failed` with an alert
(`logs/alerts.jsonl`, optional webhook). Download before success answers
409 `report_not_ready`.