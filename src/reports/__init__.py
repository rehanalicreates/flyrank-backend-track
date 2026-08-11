"""PDF report generator (week 7).

The pipeline: SQL aggregation over the task database, rendered into a PDF
artifact by a background job, stored on disk and linked (never shipped as
bytes in the job payload), with the same job contract as the triage feature
(202, status polling, idempotency, retries, alerts).
"""