"""
Repository layer for Tasks, backed by SQLite (Week 7: PDF report generator).

The Week 1 version kept tasks in a dict. A report feature needs real SQL
aggregation (COUNT, GROUP BY, strftime) over the same data the API manages,
so the store moved to SQLite. The public interface (create/get/list/update/
delete) is unchanged, so nothing in main.py or models.py had to change, and
a server database (Postgres, MySQL) can still replace SQLite later by editing
only this file.

The table lives in data/tasks.db. src/reports/queries.py opens the same file
read-only to run the aggregation the PDF report is built from.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.exceptions import TaskNotFoundError
from app.models import TaskCreate, TaskUpdate

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "tasks.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    completed   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class Task:
    """Storage representation of a task, as handed to the API layer."""

    def __init__(
        self,
        id: int,
        title: str,
        description: str | None,
        completed: bool,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        now = datetime.now(timezone.utc)
        self.id = id
        self.title = title
        self.description = description
        self.completed = completed
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def __repr__(self) -> str:
        return (
            f"Task(id={self.id}, title={self.title!r}, "
            f"completed={self.completed})"
        )


class TaskRepository:
    """SQLite-backed store for tasks, following the repository pattern."""

    def __init__(self, path: Path = DB_PATH):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()
        self._seed()

    def _seed(self) -> None:
        # Seed only when the table is empty: a restart must not duplicate the
        # three starter tasks (the old in-memory store re-seeded on every boot).
        if self._count() == 0:
            for title in ["Buy groceries", "Finish report", "Review PR"]:
                self.create(TaskCreate(title=title))

    # -- row helpers --------------------------------------------------------

    def _count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()
        return int(row["n"])

    @staticmethod
    def _parse_ts(raw: str) -> datetime:
        return datetime.fromisoformat(raw)

    def _row_to_task(self, row) -> Task:
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            completed=bool(row["completed"]),
            created_at=self._parse_ts(row["created_at"]),
            updated_at=self._parse_ts(row["updated_at"]),
        )

    # -- CRUD ---------------------------------------------------------------

    def create(self, data: TaskCreate) -> Task:
        """Create a new task from the provided data and store it."""
        now = datetime.now(timezone.utc)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO tasks (title, description, completed, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (data.title, data.description, int(data.completed),
                 now.isoformat(), now.isoformat()),
            )
            self._conn.commit()
        return Task(
            id=cur.lastrowid,
            title=data.title,
            description=data.description,
            completed=data.completed,
            created_at=now,
            updated_at=now,
        )

    def list_all(self) -> list[Task]:
        """Return every stored task, oldest first (empty list if none exist)."""
        rows = self._conn.execute(
            "SELECT * FROM tasks ORDER BY id ASC"
        ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def get(self, task_id: int) -> Task:
        """Retrieve a task by id, or raise TaskNotFoundError."""
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise TaskNotFoundError(task_id)
        return self._row_to_task(row)

    def update(self, task_id: int, data: TaskUpdate) -> Task:
        """Partially update a task. Only provided fields are changed."""
        sets, params = [], []
        if data.title is not None:
            sets.append("title = ?")
            params.append(data.title)
        if data.description is not None:
            sets.append("description = ?")
            params.append(data.description)
        if data.completed is not None:
            sets.append("completed = ?")
            params.append(int(data.completed))
        sets.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(task_id)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params
            )
            self._conn.commit()
        if cur.rowcount == 0:
            raise TaskNotFoundError(task_id)
        return self.get(task_id)

    def delete(self, task_id: int) -> None:
        """Delete a task by id, or raise TaskNotFoundError."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM tasks WHERE id = ?", (task_id,)
            )
            self._conn.commit()
        if cur.rowcount == 0:
            raise TaskNotFoundError(task_id)

    def clear(self) -> None:
        """Remove every task from the store (used by tests to reset state)."""
        with self._lock:
            self._conn.execute("DELETE FROM tasks")
            self._conn.commit()


# Single shared instance used by the API routes.
task_repository = TaskRepository()