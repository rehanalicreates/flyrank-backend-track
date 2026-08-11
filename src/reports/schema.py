"""HTTP-facing schemas for the PDF report feature (week 7)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    """What the client asks for when requesting a report."""

    report_type: Literal["tasks"] = "tasks"
    idempotency_key: Optional[str] = Field(None, max_length=128)


class ReportArtifact(BaseModel):
    """Metadata about the generated PDF.

    The bytes stay on disk (artifact handling, week 7 lesson: store and link,
    do not pass megabytes through JSON). The job payload only ever carries
    this link, and the client fetches the file from the download endpoint.
    """

    file_name: str
    size_bytes: int
    download_url: str
    report_type: str


class ReportAccepted(BaseModel):
    """202 answer: the job is queued, poll the status URL for the artifact."""

    job_id: str
    status: str
    status_url: str


class ReportResponse(BaseModel):
    """Status and outcome of one report job."""

    job_id: str
    idempotency_key: Optional[str] = None
    status: Literal["queued", "running", "succeeded", "failed"]
    attempts: int
    report_type: str
    artifact: Optional[ReportArtifact] = None
    summary: Optional[dict] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime