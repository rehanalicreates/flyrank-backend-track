"""HTTP-facing schemas for background jobs (BE-06)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from src.llm.schema import TriageResult

JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobResponse(BaseModel):
    """Status report for one background job."""

    job_id: str
    idempotency_key: Optional[str] = None
    status: JobStatus
    attempts: int
    result: Optional[TriageResult] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobAccepted(BaseModel):
    """What the API answers immediately: 202 + where to look later."""

    job_id: str
    status: str
    status_url: str