"""The worker pool (BE-06).

Sits between the queue and the job store. Rules the worker enforces:

1. "Jobs will run twice." A job is re-enqueued on restart if it was left in
   queued/running - and that is SAFE because the LLM triage job is a pure
   function of its input message: re-running produces the same verdict. To
   avoid burning calls, a job in "succeeded"/"failed" state is never executed
   again, and duplicate queue entries collapse onto the same single execution.
2. "Jobs will fail." An attempt that raises is retried up to JOB_MAX_ATTEMPTS
   with exponential backoff plus jitter; past that the job is marked failed.
3. "Someone must find out." A final failure raises an alert (alerts.jsonl and
   optional webhook).

The LLM call itself is blocking, so it runs in a thread pool
(asyncio.to_thread) - the event loop stays free to serve requests, which is
the whole point of the async endpoint answering with 202 instantly.
"""

import asyncio
import random

from src.bg.alerts import alert_job_failed
from src.bg.settings import get_bg_settings
from src.bg.store import JobStore
from src.llm.clients import LLMClient
from src.llm.service import triage_message
from src.llm.settings import get_settings


def _backoff_with_jitter(attempt: int) -> float:
    """Exponential backoff plus jitter, mirroring the LLM client policy."""
    return min(2 ** (attempt - 1), 8) + random.uniform(0, 1)


# Pool-wide guard: a job may only be executed by one worker at a time, even if
# restart replay produced duplicate queue tokens. Single-threaded asyncio
# makes check-then-add atomic for our purposes.
_IN_FLIGHT: set = set()


class JobWorker:
    def __init__(self, store: JobStore, cfg=None):
        self.store = store
        self.cfg = cfg or get_bg_settings()
        self.queue: asyncio.Queue = asyncio.Queue()

    # -- entry points ------------------------------------------------------

    def enqueue(self, job_id: str) -> None:
        """Called from the request path (task-safe; just puts a token)."""
        self.queue.put_nowait(job_id)

    async def requeue_interrupted(self) -> None:
        """Startup: re-enqueue jobs that a previous process never finished."""
        for job_id in self.store.interrupted_jobs():
            # Cap report: keep only a queued-state line so retry starts fresh.
            self.store.touch(job_id, status="queued")
            self.queue.put_nowait(job_id)

    # -- execution ---------------------------------------------------------

    async def run(self) -> None:
        """Worker loop: take a token, execute one job, repeat forever."""
        while True:
            job_id = await self.queue.get()
            if job_id in _IN_FLIGHT:
                self.queue.task_done()
                continue  # duplicate token (restart replay): already running
            _IN_FLIGHT.add(job_id)
            try:
                await self._execute(job_id)
            except Exception:
                self.store.touch(job_id, status="failed", error="worker_crash")
                await alert_job_failed(job_id, "worker_crash", self.store.get(job_id)["attempts"])
            finally:
                _IN_FLIGHT.discard(job_id)
                self.queue.task_done()

    async def _execute(self, job_id: str) -> None:
        job = self.store.get(job_id)
        max_attempts = self.cfg["max_attempts"]

        if job is None or job["status"] == "succeeded":
            return  # replay-safe: duplicates collapse, done means done
        if job["status"] == "failed" and job["attempts"] >= max_attempts:
            return  # already gave up; nothing left to try

        self.store.touch(job_id, status="running", attempts=job["attempts"] + 1)
        try:
            client = LLMClient(cfg=get_settings())
            result = await asyncio.to_thread(triage_message, job["message"], client)
            self.store.touch(job_id, status="succeeded", result=result.model_dump(), error=None)
        except Exception as exc:  # noqa: BLE001 - every LLM failure is retryable at job level
            attempts = self.store.get(job_id)["attempts"]
            if attempts >= max_attempts:
                self.store.touch(job_id, status="failed", error=str(exc)[:500])
                await alert_job_failed(job_id, str(exc)[:500], attempts)
            else:
                self.store.touch(job_id, status="queued", error=str(exc)[:500])
                await asyncio.sleep(_backoff_with_jitter(attempts))
                self.queue.put_nowait(job_id)