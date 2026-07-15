from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from app.exceptions import TaskNotFoundError
from app.models import TaskCreate, TaskUpdate, TaskResponse
from app.repository import task_repository

app = FastAPI(title="Task API", version="1.0.0")


@app.exception_handler(TaskNotFoundError)
async def task_not_found_handler(request: Request, exc: TaskNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "task_not_found", "message": str(exc)},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    title_errors = ("missing", "value_error", "string_too_short")
    has_title_error = any(
        err.get("loc") == ("body", "title") and err.get("type") in title_errors
        for err in exc.errors()
    )
    if has_title_error:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "validation_error",
                "message": "Title is required and must not be empty.",
            },
        )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


@app.get("/")
def root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(payload: TaskCreate):
    return task_repository.create(payload)


@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks():
    return task_repository.list_all()


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int):
    return task_repository.get(task_id)
