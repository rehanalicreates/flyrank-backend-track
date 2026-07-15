from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from app.exceptions import TaskNotFoundError
from app.models import TaskResponse
from app.repository import task_repository

app = FastAPI(title="Task API", version="1.0.0")


@app.exception_handler(TaskNotFoundError)
async def task_not_found_handler(request: Request, exc: TaskNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "task_not_found", "message": str(exc)},
    )


@app.get("/")
def root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks():
    return task_repository.list_all()


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    return task_repository.get(task_id)
