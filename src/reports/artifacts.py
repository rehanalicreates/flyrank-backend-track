"""Artifact handling (week 7 lesson: store and link, do not pass bytes around).

Generated PDFs live under data/reports/. The job result references a file by
name and URL; the download endpoint resolves the name back to a path. The
job id pattern is validated before it is ever joined into a path, so an
untrusted job_id cannot escape the reports directory.
"""

import re
from pathlib import Path

SAFE_REPORT_ID = re.compile(r"^report_[0-9a-f]{12}$")


def artifact_path(reports_dir: Path, job_id: str) -> Path:
    """Resolve a validated report job id to its PDF path on disk."""
    if not SAFE_REPORT_ID.match(job_id):
        raise ValueError(f"unsafe report job id: {job_id}")
    return reports_dir / f"{job_id}.pdf"