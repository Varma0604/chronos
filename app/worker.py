import json
import logging
import time
from datetime import datetime, timedelta, timezone

from app.database import Base, SessionLocal, engine
from app.models import Task
from app.queue import client, pop_due, requeue_stale_rows

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chronos.worker")


def execute(kind: str, payload: dict):
    if kind == "echo":
        return payload.get("value")
    if kind == "sum":
        values = payload.get("values")
        if not isinstance(values, list) or not all(isinstance(x, (int, float)) for x in values):
            raise ValueError("sum task requires a numeric 'values' array")
        return sum(values)
    raise ValueError(f"Unknown task kind: {kind}")


def run_once():
    task_id = pop_due()
    if not task_id:
        return False
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task or task.status not in {"queued", "retrying"}:
            return True
        task.status = "running"
        task.attempts += 1
        db.commit()
        try:
            value = execute(task.kind, json.loads(task.payload))
            task.result = json.dumps(value)
            task.error = None
            task.status = "succeeded"
        except Exception as exc:
            task.error = str(exc)[:1000]
            if task.attempts < task.max_attempts:
                task.status = "retrying"
                delay = min(60, 2 ** (task.attempts - 1))
                task.run_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            else:
                task.status = "failed"
        db.commit()
        if task.status == "retrying":
            from app.queue import enqueue
            enqueue(task.id, task.run_at.timestamp(), task.priority)
        log.info("task=%s status=%s attempt=%s", task.id, task.status, task.attempts)
    return True


def main():
    Base.metadata.create_all(bind=engine)
    while True:
        with SessionLocal() as db:
            requeue_stale_rows(db)
        try:
            worked = run_once()
        except Exception:
            log.exception("worker iteration failed")
            worked = False
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
