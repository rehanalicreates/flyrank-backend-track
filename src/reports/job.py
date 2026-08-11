"""The report job executable (week 7): query, render, store, report back.

Runs inside the shared background worker pool (the BE-06 pattern): it is
dispatched by job kind, executes off-thread (SQL + PDF rendering are
blocking), and on success the PDF exists on disk while the job result only
carries artifact metadata: file name, size, and a download URL.

Artifact handling is the week 7 lesson: store and link, never pass 20 MB
through JSON. The client polls GET /reports/{job_id} for the link, then
fetches the file from GET /reports/{job_id}/download.
"""

from pathlib import Path

from app.repository import DB_PATH
from src.reports.queries import aggregate_tasks
from src.reports.render import render_tasks_pdf


def run_report_job(job_id: str, payload: dict, reports_dir: Path) -> dict:
    """Execute one report job; return the artifact metadata for the job store.

    Payload is currently {"report_type": "tasks"}; the shape is kept so a
    future report type (daily digest, per-user summary) only adds branches
    here without touching the worker or the job contract.
    """
    report_type = payload.get("report_type", "tasks")
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / f"{job_id}.pdf"

    stats = aggregate_tasks(DB_PATH)
    render_tasks_pdf(stats, out_path, job_id=job_id)

    return {
        "artifact": {
            "file_name": out_path.name,
            "size_bytes": out_path.stat().st_size,
            "download_url": f"/reports/{job_id}/download",
            "report_type": report_type,
        },
        "summary": stats["summary"],
    }