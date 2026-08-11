"""Output schema for the LLM triage job.

The schema is the contract between the LLM and the API. Everything the model
returns is parsed and validated against these models before the API answers,
and repairs are driven by the same schema (the model is told to fix its JSON
until it fits).
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class TriageVerdict(str, Enum):
    """The closed list of possible decisions."""

    INTERESTED = "interested"
    QUESTION = "question"
    NOT_A_FIT = "not_a_fit"
    OTHER = "other"


class TriageRequest(BaseModel):
    """What the API accepts. The message is required and must not be empty."""

    message: str = Field(..., min_length=1, max_length=2000)


class TriageResult(BaseModel):
    """What the API returns: one decision plus short human-readable reasons."""

    verdict: TriageVerdict
    reasons: List[str] = Field(
        min_length=1,
        max_length=2,
        description="One or two short reasons specific to the message.",
    )