import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Task
from app.queue import enqueue


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Chronos", description="Durable scheduled workflow engine", version="0.1.0", lifespan=lifespan)


class TaskRequest(BaseModel):
    kind: str = Field(pattern="^(echo|sum)$")
    payload: dict
    run_at: datetime | None = None
    priority: int = Field(default=5, ge=0, le=9)
    max_attempts: int = Field(default=3, ge=1, le=10)


def serialize(task: Task):
    return {"task_id": task.id, "kind": task.kind, "status": task.status, "priority": task.priority,
            "run_at": task.run_at, "attempts": task.attempts, "max_attempts": task.max_attempts,
            "result": json.loads(task.result) if task.result else None, "error": task.error}


@app.get("/health")
def health():
    return {"status": "ok", "service": "chronos"}


@app.post("/api/v1/tasks", status_code=202)
def create_task(request: TaskRequest, db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    if idempotency_key:
        existing = db.query(Task).filter(Task.idempotency_key == idempotency_key).one_or_none()
        if existing:
            return serialize(existing)
    run_at = request.run_at or datetime.now(timezone.utc)
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    task = Task(id=str(uuid.uuid4()), kind=request.kind, payload=json.dumps(request.payload), status="queued",
                priority=request.priority, run_at=run_at, max_attempts=request.max_attempts,
                idempotency_key=idempotency_key)
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Task).filter(Task.idempotency_key == idempotency_key).one()
        return serialize(existing)
    db.refresh(task)
    enqueue(task.id, run_at.timestamp(), task.priority)
    return serialize(task)


@app.get("/api/v1/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return serialize(task)


@app.get("/api/v1/tasks")
def list_tasks(db: Session = Depends(get_db), limit: int = 50):
    if not 1 <= limit <= 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")
    return [serialize(task) for task in db.query(Task).order_by(Task.created_at.desc()).limit(limit)]
