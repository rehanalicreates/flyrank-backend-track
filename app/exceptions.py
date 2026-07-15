"""
Custom exceptions for the Task domain.

Why bother with custom exceptions instead of just raising HTTPException everywhere?
Because the repository layer (repository.py) shouldn't know anything about HTTP —
it's just data storage logic. It raises a domain-specific error (TaskNotFoundError),
and the API layer (main.py) is the only place that translates that into an HTTP
status code. This separation means the repository could be reused in a CLI tool,
a background job, or a different framework without dragging FastAPI along with it.
"""


class TaskNotFoundError(Exception):
    """Raised when a task with the given id does not exist."""

    def __init__(self, task_id: int):
        self.task_id = task_id
        super().__init__(f"Task with id {task_id} was not found.")

    def __repr__(self) -> str:
        return f"TaskNotFoundError(task_id={self.task_id})"


