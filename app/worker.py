import json
import logging
import os
import socket
import time
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal, ensure_schema
from app.models import Task
from app.config import WORKER_LEASE_SECONDS
from app.queue import dead_letter, pop_due, requeue_stale_rows

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chronos.worker")
WORKER_ID = os.getenv("WORKER_ID", f"{socket.gethostname()}-{os.getpid()}")


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
        task.lease_owner = WORKER_ID
        task.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=WORKER_LEASE_SECONDS)
        db.commit()
        try:
            value = execute(task.kind, json.loads(task.payload))
            task.result = json.dumps(value)
            task.error = None
            task.status = "succeeded"
            task.lease_owner = None
            task.lease_expires_at = None
        except Exception as exc:
            task.error = str(exc)[:1000]
            task.lease_owner = None
            task.lease_expires_at = None
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
        elif task.status == "failed":
            dead_letter(task.id)
        log.info("task=%s status=%s attempt=%s", task.id, task.status, task.attempts)
    return True


def main():
    ensure_schema()
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
