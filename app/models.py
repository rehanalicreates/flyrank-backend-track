"""
Pydantic models (schemas) for the Task resource.

We separate these into three shapes on purpose:
- TaskCreate:  what the client sends when creating a task (no id, no timestamps)
- TaskUpdate:  what the client sends when updating a task (all fields optional,
               so a client can update just one field without resending everything)
- TaskResponse: what the API sends back (includes server-generated fields)

Keeping these separate is a small thing now, but it's the same principle behind
"layered architecture" — the shape of data coming IN doesn't have to match the
shape of data going OUT, and the API contract stays stable even if internal
storage changes later.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    """Schema for creating a new task — sent by the client in POST /tasks."""

    title: str = Field(..., min_length=1, max_length=200, description="Task title")
    description: Optional[str] = Field(None, max_length=1000)
    completed: bool = Field(default=False)


class TaskUpdate(BaseModel):
    """Schema for updating an existing task — all fields optional for partial updates."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    completed: Optional[bool] = None


class TaskResponse(BaseModel):
    """Schema returned by the API — includes server-generated id and timestamps."""

    id: int
    title: str
    description: Optional[str] = None
    completed: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
