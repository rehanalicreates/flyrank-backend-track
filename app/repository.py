"""
Repository layer for Tasks.

This is an in-memory store (a plain dict) standing in for a real database.
It's deliberately isolated behind a small, focused interface — create/get/list/
update/delete — so that when Week 2 ("Containerize your stack") or a later
week introduces a real database, only THIS file changes. Nothing in main.py
or models.py needs to know or care where the data actually lives.

This is the "repository pattern" Harris mentioned for the layered Next.js
architecture lecture — same idea, applied here in Python.
"""

from datetime import datetime, timezone
from itertools import count
from typing import Dict

from app.exceptions import TaskNotFoundError
from app.models import TaskCreate, TaskUpdate


class Task:
    """Internal storage representation of a task."""

    def __init__(self, id: int, title: str, description: str | None, completed: bool):
        self.id = id
        self.title = title
        self.description = description
        self.completed = completed
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at

    def __repr__(self) -> str:
        return (
            f"Task(id={self.id}, title={self.title!r}, "
            f"completed={self.completed})"
        )


class TaskRepository:
    """In-memory store for tasks, following the repository pattern."""

    def __init__(self):
        self._tasks: Dict[int, Task] = {}
        self._id_counter = count(start=1)
        self._seed()

    def _seed(self):
        for title in ["Buy groceries", "Finish report", "Review PR"]:
            self.create(TaskCreate(title=title))

    def create(self, data: TaskCreate) -> Task:
        """Create a new task from the provided data and store it."""
        task_id = next(self._id_counter)
        task = Task(
            id=task_id,
            title=data.title,
            description=data.description,
            completed=data.completed,
        )
        self._tasks[task_id] = task
        return task

    def list_all(self) -> list[Task]:
        """Return every stored task (empty list if none exist)."""
        return list(self._tasks.values())

    def get(self, task_id: int) -> Task:
        """Retrieve a task by id, or raise TaskNotFoundError."""
        task = self._tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def update(self, task_id: int, data: TaskUpdate) -> Task:
        """Partially update a task. Only provided fields are changed."""
        task = self.get(task_id)
        if data.title is not None:
            task.title = data.title
        if data.description is not None:
            task.description = data.description
        if data.completed is not None:
            task.completed = data.completed
        task.updated_at = datetime.now(timezone.utc)
        return task

    def delete(self, task_id: int) -> None:
        """Delete a task by id, or raise TaskNotFoundError."""
        task = self.get(task_id)
        del self._tasks[task.id]

    def clear(self) -> None:
        """Remove every task from the store (used by tests to reset state)."""
        self._tasks.clear()


# Single shared instance used by the API routes.
# In a real app this would be swapped for a dependency-injected DB session.
task_repository = TaskRepository()
