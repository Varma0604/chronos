import json
from datetime import datetime, timedelta, timezone

import app.queue as queue
import app.worker as worker
from app.database import SessionLocal
from app.models import Task
from app.worker import execute


def test_builtin_task_handlers():
    assert execute("echo", {"value": "hi"}) == "hi"
    assert execute("sum", {"values": [2, 3, 4]}) == 9


def test_final_handler_failure_is_sent_to_dead_letter_queue(monkeypatch):
    task_id = "dead-letter-task"
    with SessionLocal() as db:
        db.add(Task(
            id=task_id,
            kind="sum",
            payload=json.dumps({"values": "not-a-list"}),
            status="queued",
            priority=5,
            run_at=datetime.now(timezone.utc),
            max_attempts=1,
        ))
        db.commit()

    dead_letter_ids = []
    monkeypatch.setattr(worker, "pop_due", lambda: task_id)
    monkeypatch.setattr(worker, "dead_letter", dead_letter_ids.append)

    assert worker.run_once() is True
    assert dead_letter_ids == [task_id]
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task.status == "failed"
        assert task.attempts == 1
        assert "numeric" in task.error
        assert task.lease_owner is None
        assert task.lease_expires_at is None


def test_expired_worker_lease_requeues_task(monkeypatch):
    task_id = "expired-lease-task"
    with SessionLocal() as db:
        db.add(Task(
            id=task_id,
            kind="echo",
            payload=json.dumps({"value": "recover me"}),
            status="running",
            priority=5,
            run_at=datetime.now(timezone.utc),
            max_attempts=3,
            lease_owner="worker-that-crashed",
            lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        ))
        db.commit()

    requeued = []
    monkeypatch.setattr(queue, "enqueue", lambda *args: requeued.append(args))
    with SessionLocal() as db:
        queue.requeue_stale_rows(db)

    assert requeued and requeued[0][0] == task_id
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        assert task.status == "queued"
        assert task.lease_owner is None
        assert task.lease_expires_at is None
        assert "lease expired" in task.error.lower()
